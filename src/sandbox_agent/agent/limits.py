"""
Bounds on how long the agent can run, so a confused model cannot loop.

- a cap on model calls per run (ends cleanly; the user can say "continue");
- a cap on sandbox creation (the "create another one to retry" loop);
- a guard that refuses to repeat a tool call that already returned the same result twice.
"""

from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
    wrap_tool_call,
)
from langchain_core.messages import AIMessage, ToolMessage

RUN_CALLS = 40            # model calls per user message for the main agent
SUBAGENT_RUN_CALLS = 20   # model calls per delegated task
REPEAT_LIMIT = 2          # identical call + identical result this many times -> refuse the next one
LOOKBACK = 24             # only the recent history counts

REPEAT_NOTICE = (
    "Refused: you already made this exact call {n} times and got the same result each time. Repeating it "
    "will not change anything. Change your approach (read the log, fix the code, try a different command), "
    "or stop and tell the user what you found."
)


def _same_call_results(messages: list, name: str, args: dict) -> list[str]:
    """Results of earlier identical (name, args) tool calls within the lookback window."""
    recent = messages[-LOOKBACK:]
    ids = [
        c["id"] for m in recent if isinstance(m, AIMessage) for c in m.tool_calls
        if c["name"] == name and c.get("args") == args
    ]
    return [
        str(m.content) for m in recent if isinstance(m, ToolMessage) and m.tool_call_id in ids
    ]


@wrap_tool_call
async def refuse_repeats(request, handler):
    call = request.tool_call
    results = _same_call_results(request.state.get("messages", []), call["name"], call.get("args") or {})
    if len(results) >= REPEAT_LIMIT and len(set(results[-REPEAT_LIMIT:])) == 1:
        return ToolMessage(
            content=REPEAT_NOTICE.format(n=len(results)), tool_call_id=call["id"], name=call["name"], status="error"
        )
    return await handler(request)


def limits(run_calls: int = RUN_CALLS, one_sandbox: bool = True) -> list:
    stack = [ModelCallLimitMiddleware(run_limit=run_calls, exit_behavior="end")]
    if one_sandbox:
        stack.append(ToolCallLimitMiddleware(tool_name="sbx_create_sandbox", run_limit=1, exit_behavior="continue"))
    stack.append(refuse_repeats)
    return stack
