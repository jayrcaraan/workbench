"""
AG-UI agent with one fix: the arguments a model streams in the *same* chunk as a tool call's name were dropped,
so the UI showed `{}` for the whole run (the full call only arrived in the final snapshot). This emits them as
the call's first TOOL_CALL_ARGS right after TOOL_CALL_START.
"""

from collections.abc import AsyncGenerator
from typing import Any

from ag_ui.core import EventType, ToolCallArgsEvent
from copilotkit import LangGraphAGUIAgent


def _first_chunk(event: Any) -> tuple[str, str]:
    """(name, args) of the first tool-call chunk in a streamed model event, '' where absent."""
    chunk = ((event or {}).get("data") or {}).get("chunk")
    if chunk is None:
        return "", ""
    get = chunk.get if isinstance(chunk, dict) else lambda k, d=None: getattr(chunk, k, d)
    chunks = get("tool_call_chunks", None) or []
    first = chunks[0] if chunks else None
    if not first:
        return "", ""
    name, args = first.get("name"), first.get("args")
    return (name if isinstance(name, str) else ""), (args if isinstance(args, str) else "")


class ArgsAgent(LangGraphAGUIAgent):
    async def _handle_single_event(self, event: Any, state: Any) -> AsyncGenerator[Any, None]:
        name, args = _first_chunk(event)
        sent = False
        async for out in super()._handle_single_event(event, state):
            kind = getattr(out, "type", None)
            if kind == EventType.TOOL_CALL_START:
                self._open_call = out.tool_call_id
            elif kind == EventType.TOOL_CALL_ARGS:
                sent = True
            elif kind == EventType.TOOL_CALL_END:
                self._open_call = None
            yield out
            if args and name and kind == EventType.TOOL_CALL_START:
                yield ToolCallArgsEvent(type=EventType.TOOL_CALL_ARGS, tool_call_id=out.tool_call_id, delta=args)
                sent = True
        # Argument deltas arrive in the chunks after the one carrying the name; the base class lets them go.
        call = getattr(self, "_open_call", None)
        if args and not name and not sent and call:
            yield ToolCallArgsEvent(type=EventType.TOOL_CALL_ARGS, tool_call_id=call, delta=args)
