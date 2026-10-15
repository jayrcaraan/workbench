"""
One sandbox per session, shared by the main agent and every subagent.

The session's sandbox id lives in agent state. Subagents inherit the parent's state and return their
changes, so whoever creates the sandbox first records it and everyone else gets the same one back
instead of provisioning another (the user's home volume is shared either way; extra sandboxes only
cost memory and confuse routing).
"""

import asyncio
import json
import logging
import re
from typing import Any, NotRequired

from langchain.agents.middleware import AgentState, wrap_model_call, wrap_tool_call
from langchain_core.messages import ToolMessage
from langgraph.config import get_config
from langgraph.types import Command

from .. import sandbox

logger = logging.getLogger(__name__)
CREATE = "sbx_create_sandbox"
_ID = re.compile(r"sbx-[0-9a-f]{6,}")


# Parallel subagents each see their own copy of state, so two of them can both find it empty. These are
# process-wide, keyed by thread id: a lock so creation is serialized, and the sandbox it produced.
_locks: dict[str, asyncio.Lock] = {}
_known: dict[str, str] = {}


def _thread_id() -> str:
    try:
        return str(get_config().get("configurable", {}).get("thread_id") or "default")
    except RuntimeError:  # not inside a graph run
        return "default"


class SandboxState(AgentState):
    sandbox_id: NotRequired[str]


def _id_of(message: Any) -> str | None:
    text = message.content if isinstance(message.content, str) else json.dumps(message.content, default=str)
    found = _ID.search(text)
    return found.group(0) if found else None


@wrap_tool_call(state_schema=SandboxState)
async def one_sandbox_per_session(request, handler):
    call = request.tool_call
    if call["name"] != CREATE:
        return await handler(request)

    tid = _thread_id()
    async with _locks.setdefault(tid, asyncio.Lock()):
        existing = request.state.get("sandbox_id") or _known.get(tid)
        logger.info("create_sandbox requested: thread=%s state=%s known=%s", tid, request.state.get("sandbox_id"), _known.get(tid))
        if existing and await sandbox.access(existing) is not None:
            return ToolMessage(
                content=json.dumps({
                    "status": "reused", "sandbox_id": existing,
                    "note": "This session already has a sandbox. Use it; do not create another.",
                }),
                tool_call_id=call["id"], name=call["name"],
                # The caller may be a subagent whose state lacks it: write it back so the parent has it too.
            ) if request.state.get("sandbox_id") else Command(update={
                "sandbox_id": existing,
                "messages": [ToolMessage(
                    content=json.dumps({"status": "reused", "sandbox_id": existing,
                                        "note": "This session already has a sandbox. Use it; do not create another."}),
                    tool_call_id=call["id"], name=call["name"])],
            })

        result = await handler(request)
        message = result.update["messages"][-1] if isinstance(result, Command) else result
        created = _id_of(message) if isinstance(message, ToolMessage) else None
        if created:
            _known[tid] = created
            if not isinstance(result, Command):
                return Command(update={"sandbox_id": created, "messages": [result]})
        return result


@wrap_model_call(state_schema=SandboxState)
async def announce_sandbox(request, handler):
    """Tells the model which sandbox the session already has, so it uses it instead of asking for one."""
    sandbox_id = request.state.get("sandbox_id") or _known.get(_thread_id())
    if sandbox_id and request.system_message is not None:
        note = (
            f"\n\n# Session sandbox\nThis session already has a running sandbox: `{sandbox_id}`. Use it for "
            "every sandbox tool call; do not create another. The user's home directory is mounted in it."
        )
        text = request.system_message.content if isinstance(request.system_message.content, str) else str(request.system_message.content)
        request = request.override(system_message=type(request.system_message)(content=text + note))
    return await handler(request)
