"""
Chat history in SQLite.

Two things are stored on disk and served to the UI, so a restart of any process (agent, Next.js, browser)
loses nothing:

  sessions index   id, title, sandbox, timestamps       -> data/sessions.sqlite
  conversation     messages + published apps per thread -> data/threads.sqlite (the LangGraph checkpoint)
"""

import sqlite3
import time
from contextlib import closing
from typing import Any

from ag_ui_langgraph.utils import langchain_messages_to_agui
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..llm import get_model
from ..settings import get_settings
from .sessions import _config

router = APIRouter(prefix="/sessions")


def _db() -> sqlite3.Connection:
    path = get_settings().data_dir / "sessions.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute(
        "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, title TEXT NOT NULL, sandbox_id TEXT, "
        "created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)"
    )
    return con


class SessionIn(BaseModel):
    title: str | None = None
    sandbox_id: str | None = None
    created_at: int | None = None


def _row(r: sqlite3.Row) -> dict[str, Any]:
    return {"id": r["id"], "title": r["title"], "sandboxId": r["sandbox_id"], "createdAt": r["created_at"]}


@router.get("")
async def list_sessions() -> list[dict[str, Any]]:
    with closing(_db()) as con:
        return [_row(r) for r in con.execute("SELECT * FROM sessions ORDER BY created_at DESC")]


@router.put("/{thread_id}")
async def upsert_session(thread_id: str, body: SessionIn) -> dict[str, Any]:
    _config(thread_id)  # validates the id
    now = int(time.time() * 1000)
    with closing(_db()) as con, con:
        cur = con.execute("SELECT * FROM sessions WHERE id=?", (thread_id,)).fetchone()
        if cur is None:
            con.execute(
                "INSERT INTO sessions (id, title, sandbox_id, created_at, updated_at) VALUES (?,?,?,?,?)",
                (thread_id, body.title or "New session", body.sandbox_id, body.created_at or now, now),
            )
        else:
            con.execute(
                "UPDATE sessions SET title=?, sandbox_id=?, updated_at=? WHERE id=?",
                (body.title or cur["title"], body.sandbox_id or cur["sandbox_id"], now, thread_id),
            )
        return _row(con.execute("SELECT * FROM sessions WHERE id=?", (thread_id,)).fetchone())


@router.delete("/{thread_id}", status_code=204)
async def delete_session(thread_id: str, request: Request) -> None:
    _config(thread_id)
    with closing(_db()) as con, con:
        con.execute("DELETE FROM sessions WHERE id=?", (thread_id,))
    saver = getattr(request.app.state.graph, "checkpointer", None)
    if saver is not None and hasattr(saver, "adelete_thread"):
        await saver.adelete_thread(thread_id)


@router.get("/{thread_id}/history")
async def history(thread_id: str, request: Request) -> dict[str, Any]:
    """The conversation as AG-UI messages, plus the published apps, straight from the checkpoint."""
    state = await request.app.state.graph.aget_state(_config(thread_id))
    values = state.values or {}
    messages = langchain_messages_to_agui(list(values.get("messages", [])))
    return {
        "messages": [m.model_dump(by_alias=True, exclude_none=True) for m in messages],
        "apps": values.get("apps", []),
        "sandbox_id": values.get("sandbox_id"),
    }


TITLE_PROMPT = (
    "Name this chat by the user's intent in 2 to 5 words, as a short noun phrase (for example "
    "'Sales dashboard', 'Expense tracker', 'Clean customer data'). No quotes, no trailing punctuation, "
    "no 'chat' or 'conversation'. Reply with the title only.\n\nUser request:\n{request}"
)


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") in ("text", "output_text"))
    return ""


def clean_title(raw: str, fallback: str) -> str:
    title = " ".join(raw.replace('"', "").replace("'", "").replace("`", "").split()).strip(" .:-")
    if not title or len(title.split()) > 8:
        words = fallback.split()
        title = " ".join(words[:5]) + ("…" if len(words) > 5 else "")
    return title[:48]


@router.post("/{thread_id}/title")
async def make_title(thread_id: str, request: Request) -> dict[str, Any]:
    """Names the session after the user's intent. Falls back to the first words when the model is unavailable."""
    state = await request.app.state.graph.aget_state(_config(thread_id))
    first = next((_text(m.content) for m in state.values.get("messages", []) if getattr(m, "type", "") == "human"), "")
    if not first.strip():
        raise HTTPException(409, "nothing to title yet")
    try:
        reply = await get_model(temperature=0).ainvoke(TITLE_PROMPT.format(request=first[:800]))
        raw = _text(reply.content)
    except Exception:
        raw = ""
    title = clean_title(raw, first.strip())
    with closing(_db()) as con, con:
        con.execute(
            "INSERT INTO sessions (id, title, sandbox_id, created_at, updated_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET title=excluded.title, updated_at=excluded.updated_at",
            (thread_id, title, None, int(time.time() * 1000), int(time.time() * 1000)),
        )
    return {"title": title}
