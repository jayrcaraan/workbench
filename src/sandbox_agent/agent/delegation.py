"""
Guards that make delegation to subagents trustworthy.

Observed failures: a subagent returned an empty report and the main agent told the user the app was
"ready" without ever publishing it; and the main agent sent the same `task` twice in parallel.
"""

from langchain.agents.middleware import wrap_model_call, wrap_tool_call
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from .session import _thread_id

TASK = "task"

EMPTY_REPORT = (
    "The subagent returned no report, so you do NOT know whether it worked. Do not tell the user it is "
    "done. Verify with a read-only tool (sbx_list_apps, sbx_list_files) or delegate to `debugger` once; "
    "if you still cannot confirm it, tell the user plainly that you could not finish."
)

PUBLISH_NUDGE = (
    "You delegated work this turn but have not called publish_app, and nothing was shown to the user. "
    "If you built an app: call publish_app now using the sandbox_id and app name from the builder's report "
    "(or, if the report says it failed, tell the user what failed). If no app was involved, answer normally. "
    "Never say an app is ready unless publish_app returned 'Published'."
)

DUPLICATE = "Duplicate: an identical call is already running. Wait for its result instead of repeating it."

_inflight: set[tuple[str, str, str]] = set()


def _args_key(args: dict) -> str:
    return repr(sorted((args or {}).items()))


@wrap_tool_call
async def guard_task(request, handler):
    call = request.tool_call
    # Keyed by thread: parallel tool calls each get their own copy of state.
    key = (_thread_id(), call["name"], _args_key(call.get("args")))
    # Parallel identical calls (the model sometimes emits the same `task` twice) run once.
    if call["name"] == TASK and key in _inflight:
        return ToolMessage(content=DUPLICATE, tool_call_id=call["id"], name=call["name"], status="error")
    if call["name"] == TASK:
        _inflight.add(key)
    try:
        result = await handler(request)
    finally:
        _inflight.discard(key)
    if call["name"] == TASK and isinstance(result, ToolMessage) and not str(result.content).strip():
        return result.model_copy(update={"content": EMPTY_REPORT, "status": "error"})
    return result


def _this_turn(messages: list) -> list:
    last_user = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=-1)
    return messages[last_user + 1:]


def _delegated_without_publishing(messages: list) -> bool:
    turn = _this_turn(messages)
    called_task = any(isinstance(m, AIMessage) and any(c["name"] == TASK for c in m.tool_calls) for m in turn)
    published = any(isinstance(m, ToolMessage) and "Published" in str(m.content) for m in turn)
    already_nudged = any(isinstance(m, HumanMessage) and m.content == PUBLISH_NUDGE for m in messages)
    return called_task and not published and not already_nudged


@wrap_model_call
async def require_publish_after_delegation(request, handler):
    response = await handler(request)
    last = response.result[-1] if response.result else None
    final_answer = isinstance(last, AIMessage) and not last.tool_calls
    if final_answer and _delegated_without_publishing(list(request.messages)):
        request = request.override(messages=[*request.messages, HumanMessage(content=PUBLISH_NUDGE)])
        response = await handler(request)
    return response
