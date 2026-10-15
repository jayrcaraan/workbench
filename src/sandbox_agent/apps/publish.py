"""
`publish_app`: the one custom agent tool. It attaches a declarative UI spec to an
app the agent already exposed with `sbx_expose_port`, and writes it to shared
agent state (`state.apps`) so the CopilotKit canvas can render it.
"""

import asyncio
import json
import re
from typing import Annotated, Any, NotRequired

import httpx
from deepagents.graph import DeepAgentState
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from pydantic import TypeAdapter, ValidationError

from .. import sandbox
from .spec import UiSpec


def merge_apps(old: list[dict] | None, new: list[dict] | None) -> list[dict]:
    """Reducer: apps are keyed by app_id, so re-publishing updates in place."""
    merged = {a["app_id"]: a for a in (old or [])}
    for app in new or []:
        if app.get("replaces"):  # an app resumed in a new sandbox supersedes its old entry
            merged.pop(app["replaces"], None)
            app = {k: v for k, v in app.items() if k != "replaces"}
        merged[app["app_id"]] = app
    return list(merged.values())


def build_recipe(messages: list, name: str) -> dict[str, Any] | None:
    """
    How an exposed app was brought up in this conversation: the setup installs, the start command and the
    port. Replaying it in a fresh sandbox resumes the app (its files and data live in the shared home).
    """
    calls = [c for m in messages if getattr(m, "type", "") == "ai" for c in (getattr(m, "tool_calls", None) or [])]
    expose_at = next(
        (i for i in range(len(calls) - 1, -1, -1)
         if calls[i]["name"].endswith("expose_port") and (calls[i]["args"].get("name") or "app") == name),
        None,
    )
    if expose_at is None:
        return None
    port = calls[expose_at]["args"].get("internal_port")
    before = calls[:expose_at]
    starts = [c for c in before if c["name"].endswith("start_background")]
    start = next((c for c in reversed(starts) if port and str(port) in str(c["args"].get("command", ""))), None) \
        or (starts[-1] if starts else None)
    if start is None or not port:
        return None
    setup = [
        c["args"]["command"] for c in before
        if c["name"].endswith("run_command")
        and re.search(r"\b(pip|pip3|npm|yarn)\s+(install|i)\b", str(c["args"].get("command", "")))
    ]
    a = start["args"]
    return {
        "name": name,
        "port": int(port),
        "setup": setup[-6:],
        "start": {"command": a.get("command", ""), "workdir": a.get("workdir"), "log_file": a.get("log_file")},
    }


def app_entry(sandbox_id: str, name: str, title: str, spec: dict[str, Any], access: dict[str, Any],
              app_url: str, recipe: dict[str, Any] | None) -> dict[str, Any]:
    """The `state.apps` entry for a published app (iframe apps get their direct, token-bearing URL)."""
    spec = dict(spec)
    if spec["kind"] == "iframe":
        # An iframe must load the app at its own origin, so it gets a direct URL.
        # This is the one place a sandbox token is handed to the browser.
        spec["url"] = f"{app_url.rstrip('/')}{spec.get('path', '/')}?token={access['token']}"
    entry: dict[str, Any] = {"app_id": f"{sandbox_id}/{name}", "name": name, "title": title, "ui": spec}
    if recipe:
        entry["recipe"] = recipe
    return entry


class AppsState(DeepAgentState):
    """Agent state plus the published apps, which AG-UI streams to the canvas."""

    apps: Annotated[list[dict[str, Any]], merge_apps]
    sandbox_id: NotRequired[str]  # this session's sandbox, shared with subagents (agent/session.py)


PROBE_ATTEMPTS = 6
PROBE_DELAY_S = 1.0


async def probe(url: str, token: str) -> str | None:
    """
    GETs url through the ingress. Returns None when the app answers 2xx/3xx, else a short
    reason the agent can act on. 5xx and connection errors are retried (an app that is
    still booting); a 4xx is final.
    """
    reason = "no response"
    for attempt in range(PROBE_ATTEMPTS):
        try:
            resp = await sandbox.send("GET", url, token, timeout=5.0)
            await resp.aclose()
        except httpx.HTTPError as e:
            reason = f"{type(e).__name__}: {e}"
        else:
            if resp.status_code < 400:
                return None
            if resp.status_code < 500:
                return f"{url} answered HTTP {resp.status_code}: that route does not exist or does not allow GET"
            reason = f"HTTP {resp.status_code}"
        if attempt < PROBE_ATTEMPTS - 1:
            await asyncio.sleep(PROBE_DELAY_S)
    return (
        f"{url} did not answer successfully ({reason}). This check runs from outside the sandbox, so "
        "do NOT curl that public URL from inside the sandbox (it cannot resolve it). Instead: "
        "(1) `curl -s localhost:<port>/<route>` inside the sandbox; if that fails the process is dead or "
        "crashed: read its log with sbx_read_file, fix, kill the old process and restart with "
        "sbx_start_background on the SAME port. (2) If localhost works, check `sbx_list_apps` shows this name "
        "with the right port, wait ~10 seconds (a new sandbox's ingress needs time) and call publish_app again."
    )


def _probe_path(spec: dict[str, Any]) -> str:
    """Route to check before publishing: the one the UI will load first."""
    kind = spec["kind"]
    if kind in ("table", "sheet"):
        return spec["list"]["path"]
    if kind == "metrics":
        return spec["source"]["path"]
    if kind == "iframe":
        return spec.get("path", "/")
    return "/"  # form: only reachability can be checked without side effects


_UI = TypeAdapter(UiSpec)


def columns_from_fields(declared: dict[str, Any]) -> list[dict[str, Any]]:
    """Sheet columns from an app's own field definitions, with the row id first and read-only."""
    cols: list[dict[str, Any]] = [{"key": "id", "label": "ID", "type": "number", "editable": False}]
    for f in declared.get("fields") or []:
        if f.get("key") == "id":
            continue
        col = {"key": f["key"], "label": f.get("label") or f["key"], "type": f.get("type", "text"), "editable": True}
        if f.get("options"):
            col["options"] = list(f["options"])
        cols.append(col)
    return cols


def adopt_declared_fields(spec: dict[str, Any], declared: dict[str, Any] | None) -> dict[str, Any]:
    """
    Apps built from the record template serve `GET /fields`. Their sheet is then exactly what the app declares:
    row key `id`, update/delete on `/items/{id}`, and each column's real type and options. The model only has
    to say which app to show; restating the columns is where it went wrong (a user's "Control ID" made the row
    key and read-only, and every column came out as text).
    """
    if not declared or not declared.get("fields") or spec["kind"] not in ("table", "sheet"):
        return spec
    out = dict(spec)
    out.update(key="id", rows_path="items", columns=columns_from_fields(declared),
               list={"method": "GET", "path": "/items"}, create={"method": "POST", "path": "/items"},
               update={"method": "PUT", "path": "/items/{id}"}, delete={"method": "DELETE", "path": "/items/{id}"})
    return out


async def declared_fields(base_url: str, token: str) -> dict[str, Any] | None:
    try:
        resp = await sandbox.send("GET", f"{base_url.rstrip('/')}/fields", token, timeout=5.0)
        try:
            if resp.status_code != 200:
                return None
            data = json.loads(await resp.aread())
        finally:
            await resp.aclose()
    except (httpx.HTTPError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("fields"), list) else None


@tool
async def publish_app(
    sandbox_id: str,
    name: str,
    title: str,
    ui: dict[str, Any] | str,
    runtime: ToolRuntime,
) -> Command:
    """
    Show a micro-app in the user's canvas with a generic UI bound to its HTTP routes.
    Call this after the app is running and exposed with sbx_expose_port(name=...).
    The browser then talks to the app directly (not through you), so bulk data
    entry never has to pass through the conversation.

    Args:
        sandbox_id: Sandbox the app runs in, e.g. 'sbx-1a2b3c4d'.
        name: The name used in sbx_expose_port.
        title: Short human title for the app.
        ui: A JSON object (a JSON string is also accepted) with a "kind" of:
            "table"  {"kind","title","key","rows_path"?,"list":{route},"create"?,"update"?,"delete"?,"columns":[{"key","label"?,"type"?}]}
            "sheet"  same fields as table; typed spreadsheet grid
            "form"   {"kind","title","submit":{route},"fields":[{"key","label"?,"type"?,"required"?}]}
            "metrics" {"kind","title","source":{route},"items":[{"key","label"?,"format"?}]}
            "iframe" {"kind","title","path"?}
            A route is {"method":"GET|POST|PUT|PATCH|DELETE","path":"/relative/path"}; "{id}" in a path is
            replaced by the row's key. Example table:
            {"kind":"table","title":"Tasks","key":"id","rows_path":"items",
             "list":{"method":"GET","path":"/items"},"create":{"method":"POST","path":"/items"},
             "update":{"method":"PUT","path":"/items/{id}"},"delete":{"method":"DELETE","path":"/items/{id}"},
             "columns":[{"key":"id","label":"ID","type":"number","editable":false},{"key":"title","label":"Title"}]}
    """
    call_id = runtime.tool_call_id

    def reply(text: str, update: dict | None = None) -> Command:
        msg = ToolMessage(content=text, tool_call_id=call_id)
        return Command(update={**(update or {}), "messages": [msg]})

    access = await sandbox.access(sandbox_id, fresh=True)
    if access is None:
        return reply(f"Error: sandbox {sandbox_id} does not exist. Create or recheck it first.")
    apps = {a["name"]: a for a in access.get("apps", [])}
    if name not in apps:
        known = ", ".join(sorted(apps)) or "none"
        return reply(
            f"Error: no app named {name!r} is exposed in {sandbox_id} (exposed: {known}). "
            "Call sbx_expose_port first."
        )

    # The schema the model sees is a plain object (a deeply nested union was too hard for it to emit
    # reliably); the real validation happens here, with errors it can act on.
    raw = ui
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return reply("Error: `ui` must be a JSON object (or a JSON string of one). Not published.")
    # An app built from the record template declares its own fields: the sheet is built from those, so a short
    # `{"kind": "sheet", "title": ...}` is enough and cannot disagree with the app.
    if isinstance(raw, dict) and raw.get("kind") in ("table", "sheet"):
        declared = await declared_fields(apps[name]["url"], access["token"])
        raw = adopt_declared_fields({**raw, "title": raw.get("title") or title}, declared)
    try:
        spec = _UI.validate_python(raw).model_dump(exclude_none=True)
    except ValidationError as e:
        problems = "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()[:6])
        return reply(f"Error: invalid ui spec, not published. Fix and call publish_app again. Problems: {problems}")

    # Refuse to show a broken app: the user would just see an empty error card.
    probe_path = _probe_path(spec).replace("{", "").replace("}", "")
    problem = await probe(f"{apps[name]['url'].rstrip('/')}{probe_path}", access["token"])
    if problem:
        return reply(f"Error: not published. {problem}")

    recipe = build_recipe(list(runtime.state.get("messages", [])), name)
    app = app_entry(sandbox_id, name, title, spec, access, apps[name]["url"], recipe)
    return reply(
        f"Published '{title}' ({app['app_id']}) as a {spec['kind']}. The user can now see it.",
        {"apps": [app]},
    )
