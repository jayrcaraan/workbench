"""
Session sandboxes: the UI starts a session's sandbox itself, so nobody has to ask the agent for one.

The sandbox id is written into the thread's state, which is where the agent's one-sandbox-per-session
guard (agent/session.py) and its prompt read it from. The home volume is shared, so this is the same
filesystem every other sandbox of the user sees.
"""

import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from .. import sandbox
from ..agent import session as session_guard

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions")

SANDBOX_TTL_MINUTES = 120
_THREAD = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def _config(thread_id: str) -> dict[str, Any]:
    if not _THREAD.match(thread_id):
        raise HTTPException(400, "invalid thread id")
    return {"configurable": {"thread_id": thread_id}}


async def _current(graph: Any, thread_id: str) -> str | None:
    state = await graph.aget_state(_config(thread_id))
    existing = state.values.get("sandbox_id") or session_guard._known.get(thread_id)
    if existing and await sandbox.access(existing) is not None:
        return existing
    return None


@router.get("/{thread_id}/sandbox")
async def get_sandbox(thread_id: str, request: Request) -> dict[str, Any]:
    current = await _current(request.app.state.graph, thread_id)
    return {"sandbox_id": current, "state": "ready" if current else "none"}


@router.post("/{thread_id}/sandbox")
async def ensure_sandbox(thread_id: str, request: Request) -> dict[str, Any]:
    graph = request.app.state.graph
    config = _config(thread_id)
    async with session_guard._locks.setdefault(thread_id, __import__("asyncio").Lock()):
        existing = await _current(graph, thread_id)
        if existing:
            return {"sandbox_id": existing, "state": "ready", "created": False}
        try:
            created = await sandbox.call("create_sandbox", ttl_minutes=SANDBOX_TTL_MINUTES)
        except Exception as e:
            logger.exception("could not start the session sandbox")
            raise HTTPException(502, f"Could not start a sandbox: {e}") from e
        sandbox_id = created["sandbox_id"]
        session_guard._known[thread_id] = sandbox_id
        await graph.aupdate_state(config, {"sandbox_id": sandbox_id})
        return {"sandbox_id": sandbox_id, "state": "ready", "created": True}


class ResumeError(Exception):
    pass


@router.post("/{thread_id}/apps/{name}/resume")
async def resume_app(thread_id: str, name: str, request: Request) -> dict[str, Any]:
    """
    Brings an app back after its sandbox expired: starts a new sandbox for the session if needed, replays the
    app's recorded start recipe (files and data are in the shared home), re-exposes it and republishes it.
    No model involved.
    """
    from ..apps.publish import _probe_path, app_entry, probe

    graph = request.app.state.graph
    config = _config(thread_id)
    state = await graph.aget_state(config)
    apps = [a for a in state.values.get("apps", []) if a.get("name") == name]
    if not apps:
        raise HTTPException(404, f"no published app named {name!r} in this session")
    old = apps[-1]
    recipe = old.get("recipe")
    if not recipe:
        raise HTTPException(409, "This app has no start recipe (it predates resume). Ask the agent to restart it.")

    ensured = await ensure_sandbox(thread_id, request)
    sandbox_id = ensured["sandbox_id"]
    try:
        for cmd in recipe.get("setup", []):
            await sandbox.call("run_command", sandbox_id=sandbox_id, command=cmd, timeout_seconds=300)
        start = recipe["start"]
        args = {k: v for k, v in {"command": start["command"], "workdir": start.get("workdir"),
                                  "log_file": start.get("log_file")}.items() if v}
        await sandbox.call("start_background", sandbox_id=sandbox_id, **args)
        await sandbox.call("expose_port", sandbox_id=sandbox_id, internal_port=recipe["port"], name=name)
    except Exception as e:
        logger.exception("resume failed")
        raise HTTPException(502, f"Could not restart the app: {e}") from e

    access = await sandbox.access(sandbox_id, fresh=True)
    live = next((a for a in (access or {}).get("apps", []) if a["name"] == name), None)
    if not access or live is None:
        raise HTTPException(502, "The app did not come back (it is not exposed in the new sandbox).")
    spec = {k: v for k, v in old["ui"].items() if k != "url"}
    problem = await probe(f"{live['url'].rstrip('/')}{_probe_path(spec).replace('{', '').replace('}', '')}", access["token"])
    if problem:
        raise HTTPException(502, f"The app was restarted but does not answer yet: {problem}")
    entry = app_entry(sandbox_id, name, old["title"], spec, access, live["url"], recipe)
    entry["replaces"] = old["app_id"]
    await graph.aupdate_state(config, {"apps": [entry]})
    return {"app": {k: v for k, v in entry.items() if k != "replaces"}, "replaces": old["app_id"], "sandbox_id": sandbox_id}
