"""
Trims what is sent to the model on each call. The stored conversation (and what the UI shows) is untouched.

Agent runs resend the whole history every turn, and the bulk of it is tool noise: file contents the
agent wrote (as tool-call arguments), command output, listings. The gateway rate-limits input tokens
per minute, so old noise is elided while the user's messages and the most recent exchange stay intact.
"""

from langchain.agents.middleware import wrap_model_call
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

RECENT_MESSAGES = 14        # the last N messages are kept whole (apart from very large tool output)
OLD_TOOL_RESULT_CHARS = 400   # tool results older than that are cut to this many characters
RECENT_TOOL_RESULT_CHARS = 6000
OLD_ARG_CHARS = 200         # string arguments of old tool calls (e.g. file contents) are cut to this


def _cut(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}… [{len(text) - limit} more characters omitted]"


def _text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)
    return str(content)


def _trim_args(call: dict) -> dict:
    args = {k: _cut(v, OLD_ARG_CHARS) if isinstance(v, str) else v for k, v in (call.get("args") or {}).items()}
    return {**call, "args": args}


def trim_messages(messages: list[BaseMessage], recent: int = RECENT_MESSAGES) -> list[BaseMessage]:
    """Returns a shortened copy; the input list and its messages are not modified."""
    start = max(0, len(messages) - recent)
    # Never start the kept window on a tool result: it must stay with the AI message that called it.
    while start > 0 and isinstance(messages[start], ToolMessage):
        start -= 1

    out: list[BaseMessage] = []
    for i, m in enumerate(messages):
        if isinstance(m, ToolMessage):
            limit = RECENT_TOOL_RESULT_CHARS if i >= start else OLD_TOOL_RESULT_CHARS
            text = _text(m.content)
            out.append(m.model_copy(update={"content": _cut(text, limit)}) if len(text) > limit else m)
        elif isinstance(m, AIMessage) and i < start and m.tool_calls:
            out.append(m.model_copy(update={"tool_calls": [_trim_args(c) for c in m.tool_calls]}))
        else:
            out.append(m)  # user and system messages are always kept whole
    return out


@wrap_model_call
async def trim_context(request, handler):
    return await handler(request.override(messages=trim_messages(list(request.messages))))
