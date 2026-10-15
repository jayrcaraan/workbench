"""
`show_dashboard`: render the user's data (DuckDB / SQLite / CSV / Parquet / JSON in their home) as tables
and charts, with no app to build or run.

The service runs each panel's read-only SQL inside the sandbox (through the MCP `run_command` tool), puts
the rows into the generative-UI spec, and publishes it to the canvas through shared agent state. Rows go
sandbox -> service -> browser; the model only wrote the SQL.
"""

import base64
import json
import re
import shlex

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from pydantic import TypeAdapter, ValidationError

from .. import sandbox
from .spec import DashboardSpec, Panel, PanelResult

_PANELS = TypeAdapter(list[Panel])

MAX_ROWS = 1000

# Runs inside the sandbox. Opens files read-only, accepts a single SELECT/WITH statement, prints one JSON line.
RUNNER = r'''
import base64, json, os, re, sqlite3, subprocess, sys
req = json.loads(base64.b64decode(sys.argv[1]))
out = {"columns": [], "rows": [], "truncated": False}
try:
    home = os.path.realpath(os.path.expanduser("~"))
    path = os.path.realpath(os.path.join(home, req["path"]))
    if not (path == home or path.startswith(home + os.sep)):
        raise ValueError("path must be inside the home directory")
    if not os.path.isfile(path):
        found = []
        for root, dirs, files in os.walk(home):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "__pycache__")]
            if root[len(home):].count(os.sep) >= 3:
                dirs[:] = []
            for f in files:
                if os.path.splitext(f)[1].lower() in (".db", ".sqlite", ".sqlite3", ".duckdb", ".csv", ".parquet", ".json", ".jsonl"):
                    found.append(os.path.relpath(os.path.join(root, f), home))
        raise ValueError("no such file: " + req["path"] + ". Data files in the home directory: " + (", ".join(sorted(found)[:15]) or "none"))
    sql, limit = req["sql"].strip().rstrip(";"), int(req["limit"])
    if not re.match(r"(?is)^\s*(select|with|describe|show|summarize|from)\b", sql) or ";" in sql \
       or re.search(r"(?i)\b(insert|update|delete|drop|alter|create|attach|copy|export|install|load|call|set|pragma)\b", sql):
        raise ValueError("only a single read-only SELECT/WITH statement is allowed")
    ext = os.path.splitext(path)[1].lower()
    kind = {".csv": "csv", ".tsv": "csv", ".parquet": "parquet", ".json": "json", ".jsonl": "json", ".ndjson": "json",
            ".duckdb": "duckdb", ".sqlite": "sqlite", ".sqlite3": "sqlite", ".db": "db"}.get(ext)
    if kind is None:
        raise ValueError("unsupported file type " + ext)
    if kind == "db":
        kind = "sqlite" if open(path, "rb").read(16).startswith(b"SQLite format 3") else "duckdb"
    if kind == "sqlite":
        con = sqlite3.connect("file:" + path + "?mode=ro", uri=True, timeout=5)
        cur = con.execute(sql)
    else:
        try:
            import duckdb
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "duckdb"], check=True, capture_output=True)
            import duckdb
        if kind == "duckdb":
            con = duckdb.connect(path, read_only=True)
        else:
            con = duckdb.connect(":memory:")
            q = path.replace("'", "''")
            reader = {"csv": "read_csv_auto", "parquet": "read_parquet", "json": "read_json_auto"}[kind]
            con.execute("CREATE VIEW data AS SELECT * FROM %s('%s')" % (reader, q))
        cur = con.execute(sql)
    out["columns"] = [d[0] for d in cur.description or []]
    rows = cur.fetchmany(limit + 1)
    out["truncated"] = len(rows) > limit
    def cell(v):
        return v if v is None or isinstance(v, (bool, int, float, str)) else str(v)
    out["rows"] = [[cell(v) for v in r] for r in rows[:limit]]
except Exception as e:
    out["error"] = type(e).__name__ + ": " + str(e)
print(json.dumps(out))
'''


async def run_query(sandbox_id: str, path: str, sql: str, limit: int = MAX_ROWS) -> PanelResult:
    payload = base64.b64encode(json.dumps({"path": path, "sql": sql, "limit": limit}).encode()).decode()
    res = await sandbox.call(
        "run_command", sandbox_id=sandbox_id, timeout_seconds=120,
        command=f"python3 -c {shlex.quote(RUNNER)} {payload}",
    )
    stdout = str(res.get("stdout", "")).strip().splitlines()
    try:
        return PanelResult.model_validate(json.loads(stdout[-1]))
    except (IndexError, ValueError):
        detail = (str(res.get("stderr", "")) or str(res.get("stdout", "")) or "no output").strip()[-300:]
        return PanelResult(columns=[], rows=[], error=f"could not run the query: {detail}")


DIGEST_ROWS = 15


def digest(panels: list[Panel]) -> str:
    """
    What the model may quote after a dashboard is shown: the small aggregates the chart and metric panels
    computed. Without it the model cannot know the numbers it just put on screen and invents them. Tables are
    row-level data, so only their size is reported; large results are not echoed either.
    """
    lines = []
    for panel in panels:
        r = panel.result
        if panel.type == "note" or r is None or r.error:
            continue
        if panel.type == "table" or len(r.rows) > DIGEST_ROWS:
            lines.append(f"- {panel.title}: {len(r.rows)} row(s){' (truncated)' if r.truncated else ''}, columns {r.columns} (row data not shown)")
        else:
            lines.append(f"- {panel.title}: columns {r.columns}, rows {r.rows}")
    return "\n".join(lines)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "dashboard"


@tool
async def show_dashboard(
    sandbox_id: str,
    title: str,
    panels: list[Panel] | str,
    runtime: ToolRuntime,
) -> Command:
    """
    Show data from the user's files (DuckDB, SQLite, CSV, Parquet, JSON in their home) as a dashboard in the
    user's canvas. No app is built or run: each panel's SQL is executed read-only inside the sandbox and the
    result is rendered directly. Row-level data never passes through you; you write the SQL and are told the
    small aggregates the panels computed, so you can describe them without guessing.

    Use this for "show me / summarize / chart / dashboard" requests over existing data. Call it again with the
    same title to refresh or change it.

    Args:
        sandbox_id: Sandbox whose home holds the data files, e.g. 'sbx-1a2b3c4d'.
        title: Dashboard title.
        panels: 1 to 12 panels. Each has `path` (file relative to home), `sql` (one SELECT/WITH; csv, parquet and
            json files are the table `data`), `type` (metric, table, bar, line), and `x`/`y` column names for
            bar/line (`y` for metric).
    """
    call_id = runtime.tool_call_id

    def reply(text: str, update: dict | None = None) -> Command:
        return Command(update={**(update or {}), "messages": [ToolMessage(content=text, tool_call_id=call_id)]})

    if await sandbox.access(sandbox_id) is None:
        return reply(f"Error: sandbox {sandbox_id} does not exist. Create or recheck it first.")

    if isinstance(panels, str):  # some models send the list as a JSON string
        try:
            panels = _PANELS.validate_python(json.loads(panels))
        except (ValueError, ValidationError) as e:
            return reply(f"Error: `panels` must be a list of panel objects (a JSON string of one is also accepted). {str(e)[:300]}")
    filled: list[Panel] = []
    problems: list[str] = []
    for panel in panels:
        if panel.type == "note":  # text only: nothing to run
            filled.append(panel)
            continue
        result = await run_query(sandbox_id, panel.path or "", panel.sql or "")
        if result.error:
            problems.append(f"{panel.title}: {result.error}")
        filled.append(panel.model_copy(update={"result": result}))

    if problems and len(problems) == sum(1 for p in filled if p.type != "note"):
        return reply("Error: not shown, every panel failed. " + " | ".join(problems) + " Fix the SQL or the file path and call again.")

    spec = DashboardSpec(kind="dashboard", title=title, panels=filled).model_dump(exclude_none=True)
    app = {"app_id": f"{sandbox_id}/dashboard-{_slug(title)}", "name": f"dashboard-{_slug(title)}", "title": title, "ui": spec}
    note = f" Panels with problems: {' | '.join(problems)}" if problems else ""
    values = digest(filled)
    seen = f"\nValues the panels computed (the only numbers you may quote; never invent others):\n{values}" if values else ""
    return reply(f"Showing '{title}' with {len(filled)} panel(s). The user can see it now.{note}{seen}", {"apps": [app]})
