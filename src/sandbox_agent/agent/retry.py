"""Model-call middleware that keeps the agent loop from ending silently."""

import logging

from langchain.agents.middleware import ModelResponse, wrap_model_call
from langchain_core.messages import AIMessage, HumanMessage

logger = logging.getLogger(__name__)

NUDGE = (
    "Your previous turn was empty (no text and no tool call). Continue the task: either call a "
    "tool or reply to the user in plain text."
)
# From the second retry the generic nudge is replaced by something concrete. Measured on a stuck thread: a
# generic "keep commands short" reminder fixed 0/3, a specific small next step fixed 3/3. The usual cause is
# the model attempting one long multi-line script whose tool call the gateway then fails to parse.
STEER = (
    "Your last turns produced no tool call, most likely because the command was too long. Take ONE small "
    "step now. To look at a data file, call show_dashboard with a table panel whose sql is `SHOW TABLES`, "
    "`DESCRIBE <table>` or `SELECT * FROM <table> LIMIT 5` (for csv/parquet/json the table is `data`). "
    "Otherwise run a single short one-line command: no heredocs, no multi-line scripts, write long code "
    "to a file with write_file first."
)
EMPTY_TURN_RETRIES = 3
FORCE_TOOL_FROM_RETRY = 2  # from this retry on, require a tool call
GIVE_UP = (
    "I did not manage to continue: the model returned no output for this step. Say “continue” to try "
    "again, or rephrase what you want."
)


def _is_empty(last: object) -> bool:
    if not isinstance(last, AIMessage) or last.tool_calls:
        return False
    parts = last.content if isinstance(last.content, list) else [last.content]
    return not "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in parts).strip()


@wrap_model_call
async def retry_empty_turn(request, handler):
    """
    gpt-oss sometimes decides on a tool call in its reasoning and then emits nothing (no text, no tool
    call). LangGraph treats that as "finished", so the user would see a stalled chat. Re-ask: first with a
    nudge, then forcing a tool call (`tool_choice="required"`, which the gateway honours). If it is still
    empty, say so in the chat instead of going quiet.
    """
    response = await handler(request)
    for attempt in range(1, EMPTY_TURN_RETRIES + 1):
        last = response.result[-1] if response.result else None
        if not _is_empty(last):
            return response
        logger.warning("empty model turn (retry %d): %.300r | %s", attempt, last.content, last.response_metadata)
        steering = STEER if attempt >= FORCE_TOOL_FROM_RETRY else NUDGE
        overrides: dict = {"messages": [*request.messages, HumanMessage(content=steering)]}
        if attempt >= FORCE_TOOL_FROM_RETRY and request.tools:
            overrides["tool_choice"] = "required"
        request = request.override(**overrides)
        response = await handler(request)
    last = response.result[-1] if response.result else None
    if _is_empty(last):
        logger.error("model stayed empty after %d retries", EMPTY_TURN_RETRIES)
        return ModelResponse(result=[AIMessage(content=GIVE_UP)])
    return response
