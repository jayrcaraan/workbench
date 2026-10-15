"""
The Workbench collector: a small FastAPI app that runs INSIDE a sandbox and stores the user's
sheets (field definitions + rows) in the home volume, so the data survives sandboxes and is shared by
every sandbox of the same user.

This file is deployed verbatim by `workbench.provision`; it must only use what the sandbox image has
(fastapi, pydantic, stdlib). Data: $WORKBENCH_DB or ~/workbench/workbench.db (SQLite, WAL).

Every sheet is a real table `sheet_<id>` with one typed column per field (TEXT / REAL / INTEGER), so the data
is queryable with plain SQL (`SELECT sum(amount) FROM sheet_ab12...`). The `sheets` table holds the field
definitions. Older databases kept rows as JSON blobs in `rows`; those are imported the first time a sheet is read.
"""

import json
import os
import re
import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DB_PATH = Path(os.environ.get("WORKBENCH_DB") or Path.home() / "workbench" / "workbench.db")
TYPES = {"text", "number", "currency", "date", "checkbox", "select"}
KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,59}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

app = FastAPI(title="workbench-collector")


def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS sheets (id TEXT PRIMARY KEY, name TEXT NOT NULL, fields TEXT NOT NULL,
                                           created REAL DEFAULT (strftime('%s','now')));
        """
    )
    return con


class Field_(BaseModel):
    key: str
    label: str = Field(min_length=1, max_length=80)
    type: str = "text"
    options: list[str] = []


class SheetIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    fields: list[Field_] = Field(min_length=1, max_length=50)


def _check_fields(fields: list[Field_]) -> None:
    keys = [f.key.lower() for f in fields]  # SQLite column names are case-insensitive
    if len(set(keys)) != len(keys):
        raise HTTPException(422, "field keys must be unique")
    for f in fields:
        if not KEY.match(f.key):
            raise HTTPException(422, f"invalid field key {f.key!r}")
        if f.type not in TYPES:
            raise HTTPException(422, f"invalid type {f.type!r} for {f.key}")


def _clean(fields: list[dict], values: dict[str, Any]) -> dict[str, Any]:
    """Validates and normalizes one row against the sheet's fields. Unknown keys are dropped."""
    out: dict[str, Any] = {}
    for f in fields:
        k, t, v = f["key"], f["type"], values.get(f["key"])
        if v is None or v == "":
            out[k] = False if t == "checkbox" else None
            continue
        try:
            if t in ("number", "currency"):
                if isinstance(v, bool):
                    raise ValueError
                out[k] = float(str(v).replace("$", "").replace(",", "").strip()) if isinstance(v, str) else float(v)
                if out[k].is_integer():
                    out[k] = int(out[k])
            elif t == "checkbox":
                out[k] = v if isinstance(v, bool) else str(v).strip().lower() in ("true", "yes", "y", "1", "x")
            elif t == "date":
                if not DATE.match(str(v)):
                    raise ValueError
                out[k] = str(v)
            elif t == "select":
                if f.get("options") and str(v) not in f["options"]:
                    raise ValueError
                out[k] = str(v)
            else:
                out[k] = str(v)
        except ValueError:
            raise HTTPException(422, f"{f['label']}: {v!r} is not a valid {t}") from None
    return out


SQL_TYPE = {"text": "TEXT", "number": "REAL", "currency": "REAL", "date": "TEXT", "checkbox": "INTEGER", "select": "TEXT"}


def _table(sheet_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9]{1,32}", sheet_id):
        raise HTTPException(404, "sheet not found")
    return f"sheet_{sheet_id}"


def _columns(fields: list[dict]) -> list[dict]:
    return [f for f in fields if f["key"] != "id"]  # `id` is the row key


def _ensure_table(con: sqlite3.Connection, sheet_id: str, fields: list[dict]) -> str:
    """Creates the sheet's table (or adds columns for new fields) and imports legacy blob rows once."""
    table = _table(sheet_id)
    cols = _columns(fields)
    existed = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None
    defs = "".join(f', "{f["key"]}" {SQL_TYPE[f["type"]]}' for f in cols)
    con.execute(f'CREATE TABLE IF NOT EXISTS "{table}" (id INTEGER PRIMARY KEY AUTOINCREMENT{defs})')
    have = {r["name"] for r in con.execute(f'PRAGMA table_info("{table}")')}
    for f in cols:
        if f["key"] not in have:
            con.execute(f'ALTER TABLE "{table}" ADD COLUMN "{f["key"]}" {SQL_TYPE[f["type"]]}')
    if not existed:
        legacy = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='rows'").fetchone()
        if legacy:
            for r in con.execute("SELECT id, data FROM rows WHERE sheet_id=? ORDER BY id", (sheet_id,)).fetchall():
                data = json.loads(r["data"])
                names = ["id"] + [f["key"] for f in cols]
                con.execute(
                    f'INSERT INTO "{table}" ({", ".join(chr(34) + n + chr(34) for n in names)}) '
                    f'VALUES ({", ".join("?" for _ in names)})',
                    [r["id"]] + [data.get(f["key"]) for f in cols],
                )
    return table


def _row_out(r: sqlite3.Row, fields: list[dict]) -> dict[str, Any]:
    return {"id": r["id"], **{f["key"]: (bool(r[f["key"]]) if f["type"] == "checkbox" else r[f["key"]]) for f in _columns(fields)}}


def _sheet(con: sqlite3.Connection, sheet_id: str) -> sqlite3.Row:
    row = con.execute("SELECT * FROM sheets WHERE id=?", (sheet_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "sheet not found")
    return row


def _view(row: sqlite3.Row, count: int | None = None) -> dict[str, Any]:
    out = {"id": row["id"], "name": row["name"], "fields": json.loads(row["fields"])}
    if count is not None:
        out["rows"] = count
    return out


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/sheets")
def list_sheets() -> dict[str, Any]:
    with closing(db()) as con:
        items = []
        for r in con.execute("SELECT * FROM sheets ORDER BY created DESC, rowid DESC").fetchall():
            table = _ensure_table(con, r["id"], json.loads(r["fields"]))
            items.append(_view(r, con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]))
        con.commit()
    return {"items": items}


@app.post("/sheets", status_code=201)
def create_sheet(body: SheetIn) -> dict[str, Any]:
    _check_fields(body.fields)
    sheet_id = uuid.uuid4().hex[:12]
    with closing(db()) as con, con:
        fields = [f.model_dump() for f in body.fields]
        con.execute("INSERT INTO sheets (id, name, fields) VALUES (?,?,?)", (sheet_id, body.name, json.dumps(fields)))
        _ensure_table(con, sheet_id, fields)
        return _view(_sheet(con, sheet_id), 0)


@app.get("/sheets/{sheet_id}")
def get_sheet(sheet_id: str) -> dict[str, Any]:
    with closing(db()) as con:
        return _view(_sheet(con, sheet_id))


@app.put("/sheets/{sheet_id}")
def update_sheet(sheet_id: str, body: SheetIn) -> dict[str, Any]:
    _check_fields(body.fields)
    with closing(db()) as con, con:
        _sheet(con, sheet_id)
        fields = [f.model_dump() for f in body.fields]
        con.execute("UPDATE sheets SET name=?, fields=? WHERE id=?", (body.name, json.dumps(fields), sheet_id))
        _ensure_table(con, sheet_id, fields)  # new fields become new columns; removed ones are kept, not dropped
        return _view(_sheet(con, sheet_id))


@app.delete("/sheets/{sheet_id}", status_code=204)
def delete_sheet(sheet_id: str) -> None:
    with closing(db()) as con, con:
        _sheet(con, sheet_id)
        con.execute(f'DROP TABLE IF EXISTS "{_table(sheet_id)}"')
        con.execute("DELETE FROM sheets WHERE id=?", (sheet_id,))


@app.get("/sheets/{sheet_id}/rows")
def list_rows(sheet_id: str) -> dict[str, Any]:
    with closing(db()) as con, con:
        fields = json.loads(_sheet(con, sheet_id)["fields"])
        table = _ensure_table(con, sheet_id, fields)
        rows = con.execute(f'SELECT * FROM "{table}" ORDER BY id').fetchall()
    return {"items": [_row_out(r, fields) for r in rows]}


@app.post("/sheets/{sheet_id}/rows", status_code=201)
def create_rows(sheet_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """One row object, or {"items": [...]} for many. Returns the stored rows in order."""
    incoming = body["items"] if isinstance(body.get("items"), list) else [body]
    if len(incoming) > 5000:
        raise HTTPException(413, "at most 5000 rows per request")
    with closing(db()) as con, con:
        fields = json.loads(_sheet(con, sheet_id)["fields"])
        table = _ensure_table(con, sheet_id, fields)
        cols = _columns(fields)
        cleaned = [_clean(fields, r if isinstance(r, dict) else {}) for r in incoming]  # all or nothing
        names = ", ".join(f'"{f["key"]}"' for f in cols)
        marks = ", ".join("?" for _ in cols)
        sql = f'INSERT INTO "{table}" ({names}) VALUES ({marks})' if cols else f'INSERT INTO "{table}" DEFAULT VALUES'
        out = []
        for data in cleaned:
            cur = con.execute(sql, [data[f["key"]] for f in cols])
            out.append({"id": cur.lastrowid, **data})
    return {"items": out}


@app.put("/sheets/{sheet_id}/rows/{row_id}")
def update_row(sheet_id: str, row_id: int, body: dict[str, Any]) -> dict[str, Any]:
    with closing(db()) as con, con:
        fields = json.loads(_sheet(con, sheet_id)["fields"])
        table = _ensure_table(con, sheet_id, fields)
        cur = con.execute(f'SELECT * FROM "{table}" WHERE id=?', (row_id,)).fetchone()
        if cur is None:
            raise HTTPException(404, "row not found")
        merged = {**_row_out(cur, fields), **{k: v for k, v in body.items() if k != "id"}}
        data = _clean(fields, merged)
        cols = _columns(fields)
        if cols:
            sets = ", ".join(f'"{f["key"]}"=?' for f in cols)
            con.execute(f'UPDATE "{table}" SET {sets} WHERE id=?', [data[f["key"]] for f in cols] + [row_id])
    return {"id": row_id, **data}


@app.delete("/sheets/{sheet_id}/rows/{row_id}", status_code=204)
def delete_row(sheet_id: str, row_id: int) -> None:
    with closing(db()) as con, con:
        fields = json.loads(_sheet(con, sheet_id)["fields"])
        table = _ensure_table(con, sheet_id, fields)
        con.execute(f'DELETE FROM "{table}" WHERE id=?', (row_id,))
