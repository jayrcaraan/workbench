"""
The sandbox MCP server as this service sees it.

The agent's tools come straight from the server (langchain-mcp-adapters). This module
adds what the service needs privately: the connection that carries the tenant identity,
the per-sandbox token/app lookup, and one HTTP helper for reaching apps through the
ingress. Tokens never leave this process.
"""

import asyncio
import json
import re
import time
from functools import cache
from typing import Any

import httpx
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from .settings import get_settings

SERVER = "sbx"
# Tools the LLM must not see: they return secrets meant for this service.
PRIVATE_TOOLS = {f"{SERVER}_get_sandbox_access"}
ACCESS_TTL_S = 15.0
# A just-created sandbox's Ingress takes a few seconds to be picked up by nginx.
RETRIES = 8
RETRY_DELAY_S = 1.0

@cache
def _mcp() -> MultiServerMCPClient:
    """The MCP connection. Identity is fixed at attachment: the server reads it from the
    headers, so tools need no user/session arguments."""
    cfg = get_settings()
    return MultiServerMCPClient(
        {SERVER: {
            "transport": "streamable_http",
            "url": cfg.mcp_url,
            "headers": {"X-User-Id": cfg.user_id, "X-Session-Id": cfg.session_id},
        }},
        tool_name_prefix=True,
    )


_access: dict[str, tuple[float, dict[str, Any]]] = {}
http = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0), follow_redirects=False)


_TOKEN_JSON = re.compile(r'("token"\s*:\s*")[^"]*(")')
_TOKEN_QUERY = re.compile(r"([?&]token=)[0-9A-Za-z_-]+")


def redact(value: Any) -> Any:
    """Removes sandbox tokens from tool output (JSON `"token"` fields and `?token=` URLs)."""
    if isinstance(value, str):
        return _TOKEN_QUERY.sub(r"\1[redacted]", _TOKEN_JSON.sub(r"\1[redacted]\2", value))
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact(v) for v in value)
    if isinstance(value, dict):
        return {k: "[redacted]" if k == "token" else redact(v) for k, v in value.items()}
    return value


def _redacting(tool: BaseTool) -> BaseTool:
    inner = tool.coroutine

    async def run(*args: Any, **kwargs: Any) -> Any:
        return redact(await inner(*args, **kwargs))

    tool.coroutine = run
    return tool


async def tools() -> list[BaseTool]:
    """MCP tools for the agent, minus the private ones, with tokens redacted from their output.
    The model and the browser (tool steps are shown in the chat) must never see a sandbox token."""
    return [
        _redacting(t) for t in await _mcp().get_tools(server_name=SERVER) if t.name not in PRIVATE_TOOLS
    ]


async def call(tool: str, **args: Any) -> dict[str, Any]:
    """Calls an MCP tool directly (unprefixed server name) and returns its JSON result."""
    async with _mcp().session(SERVER) as session:
        res = await session.call_tool(tool, args)
    text = res.content[0].text if res.content and hasattr(res.content[0], "text") else ""
    if res.isError:
        raise RuntimeError(text or f"{tool} failed")
    return json.loads(text) if text else {}


async def access(sandbox_id: str, *, fresh: bool = False) -> dict[str, Any] | None:
    """Token + apps for a sandbox (short TTL cache), or None when it does not exist."""
    cached = _access.get(sandbox_id)
    if cached and not fresh and time.monotonic() - cached[0] < ACCESS_TTL_S:
        return cached[1]
    async with _mcp().session(SERVER) as session:
        res = await session.call_tool("get_sandbox_access", {"sandbox_id": sandbox_id})
    text = res.content[0].text if res.content and hasattr(res.content[0], "text") else ""
    data = json.loads(text) if text and not res.isError else {}
    if not data.get("token"):
        return None
    _access[sandbox_id] = (time.monotonic(), data)
    return data


def forget(sandbox_id: str) -> None:
    _access.pop(sandbox_id, None)


async def send(
    method: str, url: str, token: str, *,
    params: Any = None, headers: dict[str, str] | None = None, content: bytes | None = None,
    timeout: float | None = None,
) -> httpx.Response:
    """
    Sends a request to an app with the sandbox token and returns the response unread
    (stream=True). Retries nginx answering for a host it does not know yet (404 from
    nginx, or 502-504 for idempotent methods) and connection errors for idempotent
    methods. Raises httpx errors once retries are exhausted.
    """
    idempotent = method in ("GET", "HEAD")
    headers = {**(headers or {}), "Authorization": f"Bearer {token}"}
    extra = {} if timeout is None else {"timeout": timeout}
    for attempt in range(RETRIES):
        last = attempt == RETRIES - 1
        try:
            req = http.build_request(method, url, params=params, headers=headers, content=content, **extra)
            resp = await http.send(req, stream=True)
        except httpx.TimeoutException:
            raise
        except httpx.HTTPError:
            if last or not idempotent:
                raise
        else:
            nginx = "nginx" in resp.headers.get("server", "").lower()
            lag = nginx and (resp.status_code == 404 or (idempotent and resp.status_code in (502, 503, 504)))
            if last or not lag:
                return resp
            await resp.aclose()
        await asyncio.sleep(RETRY_DELAY_S)
    raise AssertionError("unreachable")
