"""
Gateway between the browser and micro-apps.

Browser -> Next.js /api/apps/... -> this router -> <name>.<sandbox>.<domain>
The sandbox token is attached here and never leaves this process. The LLM is
not involved: this is the direct data path for tables, forms and metrics.
"""

import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

from .. import sandbox

logger = logging.getLogger(__name__)

FORWARD_REQUEST_HEADERS = {"content-type", "accept", "accept-language", "if-none-match", "range"}
FORWARD_RESPONSE_HEADERS = {
    "content-type", "content-length", "content-disposition", "etag", "cache-control",
    "last-modified", "content-range", "accept-ranges",
}
MAX_BODY_BYTES = 25 * 1024 * 1024

router = APIRouter()


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": code, "message": message}, status_code=status)


def _find_app(access: dict, name: str) -> dict | None:
    return next((a for a in access.get("apps", []) if a["name"] == name), None)


@router.api_route(
    "/apps/{sandbox_id}/{name}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"],
)
async def proxy(sandbox_id: str, name: str, path: str, request: Request) -> Response:
    try:
        access = await sandbox.access(sandbox_id)
        app = _find_app(access, name) if access else None
        if access and app is None:  # the route table may have changed since the cached lookup
            access = await sandbox.access(sandbox_id, fresh=True)
            app = _find_app(access, name) if access else None
    except Exception as e:  # MCP server unreachable
        logger.warning("access lookup failed: %s", e)
        return error(502, "gateway_unavailable", "Could not reach the sandbox controller.")
    if access is None:
        return error(404, "sandbox_not_found", f"Sandbox {sandbox_id} no longer exists.")
    if app is None:
        return error(404, "app_not_found", f"App {name!r} is not exposed in {sandbox_id}.")

    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return error(413, "body_too_large", "Request body exceeds the gateway limit.")

    try:
        upstream = await sandbox.send(
            request.method, f"{app['url'].rstrip('/')}/{path}", access["token"],
            params=request.query_params, content=body,
            headers={k: v for k, v in request.headers.items() if k.lower() in FORWARD_REQUEST_HEADERS},
        )
    except httpx.TimeoutException:
        return error(504, "app_timeout", f"{name} did not answer in time.")
    except httpx.HTTPError as e:
        return error(502, "app_unreachable", f"Could not reach {name}: {e}")

    if upstream.status_code == 401:
        sandbox.forget(sandbox_id)  # token no longer valid: refetch on the next call

    async def stream():
        if upstream.is_stream_consumed:  # already buffered (e.g. test transports)
            yield upstream.content
            return
        async for chunk in upstream.aiter_raw():
            yield chunk

    return StreamingResponse(
        stream(),
        status_code=upstream.status_code,
        headers={k: v for k, v in upstream.headers.items() if k.lower() in FORWARD_RESPONSE_HEADERS},
        background=BackgroundTask(upstream.aclose),
    )
