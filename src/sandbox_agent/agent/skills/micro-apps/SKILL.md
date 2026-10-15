---
name: micro-apps
description: Build, run, expose and publish a small web app (micro-app) in the user's sandbox. Use when the user wants an app, tool, tracker, spreadsheet to enter data into, form, or any UI backed by a running process. Not for merely viewing or charting existing data files (use data-wrangler).
---

# Micro-apps

A micro-app is any process that serves HTTP inside the sandbox. Everything lives under the sandbox home
directory, which is the user's durable volume: files survive across sandboxes and conversations. Use relative
paths (they resolve against home) and give each app its own directory, e.g. `tracker/main.py`.

## Step 0: pick the recipe (do this before any tool call)

| The user wants | Recipe | Code to write |
|---|---|---|
| To **see** existing data (csv/duckdb/sqlite...) | Not an app: use the `data-wrangler` skill (`show_dashboard`) | none |
| To **capture / track records** (tracker, log, list, checklist, sheet, form of fields) | `app-template.py` (one list) or the sheet collector (many sheets) | a 10-line `fields.json`, no code |
| A **custom app** (calculator, converter, small tool, special routes) | Write FastAPI yourself with `sbx_write_file`, `publish_app` as `table`/`form`/`metrics` | one file |
| A page that ships its own UI (Streamlit, static HTML) | Start it, `publish_app` as `iframe` | one file |

State your plan in 3 lines before the first tool call: *recipe, app name + port, the UI kind you will
publish*. Then execute it without re-planning; do not explore alternatives unless a step fails.

## One-shot sequence (about 7 tool calls)

1. `sbx_create_sandbox` (skip if the session has one).
2. Records app: `install_reference(sandbox_id, "app-template.py", "<app>/main.py")`, then `sbx_write_file`
   `<app>/fields.json` (see "Record apps" below). **Never retype or edit the template's code**: retyping it is how
   syntax errors get in. Custom app: `sbx_write_file` the complete file in one call.
3. `sbx_start_background` (`python -m uvicorn main:app --host 0.0.0.0 --port 8000`, workdir = app dir, log file).
4. `install_reference(sandbox_id, "smoke.py", "tools/smoke.py")` once, then
   `sbx_run_command "python ~/tools/smoke.py 8000 /health /items"`: waits for the port, hits each route, exits 0
   only if all are < 400. This replaces ad-hoc curl/wait/retry.
5. `sbx_expose_port(sandbox_id=..., internal_port=8000, name="<app>")`.
6. `publish_app(sandbox_id, "<app>", title, ui)`.
7. Reply in two sentences. Never claim it works before step 6 returned "Published".

If step 4 prints FAIL: read the log (`sbx_read_file`), fix, restart on the same port, run smoke again. That
loop is bounded: after two failed fixes, tell the user what you saw.

## Reference files (copy with `install_reference`, never retype)

| File | What it is |
|---|---|
| `app-template.py` | FastAPI + SQLite record app following all conventions, configured by a `fields.json` next to it (no code edits). Typed table columns, accurate `/docs`. Routes `/health`, `/items` (list/create/bulk), `/items/{id}` (update/delete). Publish as `sheet` or `table` with `key:"id"`, `rows_path:"items"`. |
| `sheet-collector.py` | Multi-sheet typed collector (see "Reference: a collector" below) |
| `smoke.py` | One-command smoke test (step 4) |
| `sql.py` | `python ~/tools/sql.py <db> "<SQL>"` (also `.tables`, `.schema`). The sandbox has no `sqlite3` CLI; use this to inspect or query any SQLite file |

## Record apps (`app-template.py`)

Install it, then write `fields.json` next to it. This is the whole customisation:

```json
{"title": "Trip checklist",
 "fields": [{"key": "item", "label": "Item", "type": "text"},
            {"key": "category", "label": "Category", "type": "select", "options": ["Documents", "Tech", "Clothes"]},
            {"key": "packed", "label": "Packed", "type": "checkbox"},
            {"key": "due", "label": "Pack by", "type": "date"}]}
```

- Types: `text`, `number`, `currency`, `date` (YYYY-MM-DD), `checkbox`, `select` (+ `options`). Keys: letters, digits, `_`.
- **Row id vs the user's own id.** The app always adds its own row id, `id`. A column the user calls "Control ID",
  "Ticket number" or "SKU" is just a `text` field; give it a key like `control_id`. It stays editable. Never make it
  the row key.
- **Publishing a record app is one short call**: `publish_app(sandbox_id, name, title, {"kind":"sheet","title":"..."})`.
  The columns, their types, options and the row key are read from the app's own `/fields`, so do not restate them.
- The database is `~/data/<title as snake_case>.db` (e.g. `~/data/trip_checklist.db`): tell the user that exact path.
  The folder is created for you; never `mkdir` it or pre-create the file.
- **Changing the schema later**: edit `fields.json` and restart (kill by port, `start_background` again). New fields
  become new columns; existing rows are kept. Do not rewrite `main.py` for this.
- **Adding data for the user** ("put all of it in", "add these"): POST to the app from inside the sandbox, one call
  for all rows: `curl -s -X POST localhost:8000/items -H 'content-type: application/json' -d '{"items":[{...},{...}]}'`
  (or a short python snippet for long lists). Do not change the app's code or restart it to "show" the data: the
  sheet reloads itself every few seconds, so the user sees the rows appear. Never tell them to click refresh.
- **Questions about the data** ("what's the structure", "how many packed"): `python ~/tools/sql.py ~/data/<file>.db ".schema"`
  or a `SELECT`. Install it first with `install_reference(sandbox_id, "sql.py", "tools/sql.py")`.
- **API docs**: `/docs` and `/openapi.json` of every app are public at `http://<name>.<sandbox_id>.sandbox.localhost/docs`
  and already list each field with its type; there is nothing to "make accurate".

## Workflow

1. **Sandbox.** One per conversation. Call `sbx_create_sandbox` once and remember the id. If unsure
   whether one exists, `sbx_list_apps` first. Never create a second one to "retry".
2. **Look before you build.** `sbx_list_files` on home. Earlier apps and data files may be
   there. Reuse or extend deliberately; if you create a new data file whose schema may
   differ from an old one, give it a new descriptive name.
3. **Write** the code with `sbx_write_file` (or `install_reference` for a skill reference).
4. **Run** it with `sbx_start_background`, e.g. `python -m uvicorn main:app --host 0.0.0.0 --port 8000`
   with `workdir` set to the app directory and a log file. Never `nohup ... &` inside run_command.
   Always bind `0.0.0.0` (not 127.0.0.1) and pick the port yourself.
5. **Verify inside the sandbox**: `sbx_run_command "curl -s -i localhost:<port>/<route>"`. Only `localhost:<port>`
   works from inside; the public `<name>.<sandbox>.sandbox.localhost` host does NOT resolve there, so never curl
   it. On failure read the log, fix, then restart (see Troubleshooting). Do not expose what you have not seen respond.
6. **Expose** with `sbx_expose_port(sandbox_id=..., internal_port=<port>, name=<name>)`: exactly those three
   argument names. Each app gets its own host `<name>.<sandbox_id>.sandbox.localhost`, so several apps run
   side by side on different ports. Use short lowercase names. Ports 8080 and 2019 belong to the sandbox
   gateway: use another port (8000, 3000, 5173, ...).
7. **Publish** with `publish_app(sandbox_id, name, title, ui)` so the user sees it. It probes the app
   from outside and refuses (with the reason) if it does not answer.

## External feeds and real-time data (tickers, prices, webhooks, APIs)

1. **Prove the source first, in one command, before writing any app.** From the sandbox: `curl -sS -m 10 -o /dev/null
   -w '%{http_code}' <https-url>` for REST, or a 10-line python `websockets` snippet that connects, sends the
   subscribe message and prints the first 3 frames. Only build once you have seen real data. If it fails, tell the
   user what the provider returned (429, 403, no frames) instead of rewriting the app.
2. **Prefer the browser for public streaming APIs.** A public WebSocket (Binance, Coinbase...) can be opened by the
   page itself: the data goes provider -> browser, with no proxy in the sandbox to drop connections. Ship a static
   `index.html` (served by any 10-line FastAPI/`http.server`) and publish as `iframe`. Use a server-side connection
   only when the source needs a secret or the page must not see it.
3. **Diagnose before you rewrite.** After a failure read the log and say what you saw in one line. Do not rewrite
   the whole file more than once without new evidence. Each rewrite that "tries another format" is a guess.
4. **Name things honestly.** If a requested symbol or source does not exist (e.g. a private company's ticker), say so
   in the answer and continue with the rest.

## Troubleshooting (lessons from real runs)

- **`publish_app` says the app did not answer, but `localhost:<port>` works inside the sandbox.** The ingress
  for a brand-new sandbox needs up to ~15 s. Run `sbx_list_apps` (name and port must match what you
  published), wait ~10 s (`sleep 10` via `sbx_run_command`) and call `publish_app` again. Do not start
  another server, do not create another sandbox.
- **`localhost:<port>` fails inside the sandbox.** The process died or never started. Read its log
  (`sbx_read_file`), fix the code, then free ONLY that port and restart on the SAME port:
  `sbx_run_command "pkill -f -- '[-]-port <port>'; sleep 1"` then `sbx_start_background` again. Do not move to a
  new port and leave the old process running; that is how apps end up half-exposed on two ports.
- **File tools.** Inside the sandbox use only `sbx_read_file` / `sbx_write_file` / `sbx_list_files` /
  `sbx_run_command` (`grep -rn`, `sed -i`, python). The plain `read_file`, `edit_file`, `grep`, `ls` do not see the
  sandbox (they only read `/skills/...`): using them on a sandbox path answers "not found" every time.
- **Never `pkill -f uvicorn` (or `python`).** Other apps in the sandbox are uvicorn/python processes too, e.g.
  the sheet collector on :8765, and killing them takes down data the user is entering. Always match the
  specific port or app file (`pkill -f -- '[-]-port 8000'`, `pkill -f '[v]iewer.py'`).
  **Always write the pattern with one character in brackets.** `pkill -f` also matches the shell that is running
  your command (its command line contains the pattern), so a plain `pkill -f 'uvicorn main:app'` kills its own
  shell: exit code 143 and the rest of the command (`; sleep 1`, `&& pip install`) never runs. `[u]vicorn main:app`
  matches the same processes but not the shell. Tool arguments are `path`, not `file_path`.
- **"Address already in use".** An earlier process still holds the port: kill that one by port as above, then
  restart. Prefer one process per port and one port per app.
- **Adding an app next to an existing one.** `sbx_list_apps` first. Leave running apps (especially the
  collector) alone, give the new app its own port and name, and check each with `curl localhost:<port>/...`.
- **Import errors.** `sbx_run_command "python -c 'import <module>'"` before writing code that needs it;
  `pip install` what is missing (the image has fastapi, uvicorn, httpx, pandas, numpy, streamlit, plotly, altair).
- **Your earlier tool output is trimmed.** Old file contents and command output are elided from your context to save
  tokens. If you need a file's current content, `sbx_read_file` it instead of relying on memory.
- **Do not loop.** If the same step failed twice with the same error, change something (read the log, fix the
  code) rather than retrying it. If you are stuck after a few attempts, tell the user what you found.

## Keep data out of the conversation

The user's browser talks to the app directly. Never ask the user to paste rows into chat
and never re-type their data yourself; point them at the table. When asked a question
about the data, query it inside the sandbox with `sbx_run_command` and summarize.

## Choosing a UI kind for `publish_app`

| kind | use for |
|---|---|
| `table` | record lists the user pastes into or edits. Needs list + create routes (ideally update/delete) and a `key` column |
| `sheet` | like `table` but a typed spreadsheet grid (field types text/number/currency/date/checkbox/select, paste from Excel). Prefer it when the user will enter many records |
| `form` | one submit action |
| `metrics` | read-only numbers from one route |
| `iframe` | the app ships its own UI (Streamlit, static site) |

Example (field names are exact):

```json
{"kind":"table","title":"Customers","key":"id",
 "list":{"method":"GET","path":"/customers"},
 "create":{"method":"POST","path":"/customers"},
 "update":{"method":"PUT","path":"/customers/{id}"},
 "delete":{"method":"DELETE","path":"/customers/{id}"},
 "columns":[{"key":"id","label":"ID","type":"number","editable":false},
            {"key":"name","label":"Name","type":"text"}]}
```

Column types: text, number, currency, boolean, checkbox, date, select (select columns take `options`).
`sheet` has exactly the `table` fields. Other kinds:
`{"kind":"form","title":..,"submit":{route},"fields":[{"key","label","type","required"}]}`,
`{"kind":"metrics","title":..,"source":{route},"items":[{"key","label","format"}]}`,
`{"kind":"iframe","title":..,"path":"/"}`.

## Conventions so table/form/metrics UIs work

- JSON over HTTP. Do not implement authentication; the platform handles it.
- The list route returns a JSON array, or an object holding the array (set `rows_path`
  to its key, e.g. `"items"`).
- The create route accepts one JSON object, or `{"items": [...]}` for bulk, and returns
  the stored row(s).
- Rows have a stable id column (the table `key`). Assign ids safely: a database
  sequence/autoincrement or a UUID. Never `MAX(id)+1` or `COUNT(*)+1`; the UI sends many
  rows in quick succession.
- Update and delete paths use the key as a placeholder: `/customers/{id}`.
- **Store structured data as structured data.** One table per kind of record, one typed column per field
  (`TEXT`, `INTEGER`, `REAL`; dates as ISO `YYYY-MM-DD`; booleans as `INTEGER` 0/1), a real primary key, and
  `NOT NULL` / `CHECK` / `UNIQUE` where the data implies it. Never keep a record as a JSON string in a single
  `data` column: it cannot be filtered, sorted, aggregated or joined, and the user (and `data-wrangler`) can't
  query it. Related things get their own table with a foreign key, not a nested blob. If a schema has to
  change, `ALTER TABLE ... ADD COLUMN` rather than recreating it, so existing rows survive.
- Name columns explicitly in SQL (`INSERT INTO t (a, b) VALUES ...`).
- Check a package is installed before importing it; install with pip first. For example
  pydantic's `EmailStr` needs `email-validator`, so prefer plain `str`.
- Only Python 3.11 with fastapi, uvicorn, httpx, pandas, numpy, streamlit, plotly, altair
  and pydantic are pre-installed, plus Node 20. Anything else: install it.

## Reference: a collector for typed records (spreadsheets)

When the user wants to *capture* data in a spreadsheet ("a sheet for expenses with name, amount, date..."),
deploy `references/sheet-collector.py` rather than writing an app. Do not retype it: use
`install_reference` (read it first with `read_file` at `/skills/micro-apps/references/sheet-collector.py` if you need
to adapt it). It is a small FastAPI app that:

- stores sheets (field definitions) and, for each sheet, a real table `sheet_<id>` with one typed column per field,
  in SQLite under the sandbox home (`~/workbench/workbench.db`), so the data persists, is shared by every sandbox of
  the user and can be queried with plain SQL (`SELECT sum(amount) FROM sheet_<id>`);
- validates values by field type (`text`, `number`, `currency`, `date` as YYYY-MM-DD, `checkbox`, `select` + `options`);
- exposes `GET/POST /sheets`, `GET/PUT/DELETE /sheets/{id}`, `GET/POST /sheets/{id}/rows`
  (bulk create with `{"items": [...]}`), `PUT/DELETE /sheets/{id}/rows/{row_id}`; lists return `{"items": [...]}`.

Steps:
1. `sbx_create_sandbox` (if there is none), then `install_reference(sandbox_id, "sheet-collector.py", "workbench/collector.py")`.
2. `sbx_start_background` with `python -m uvicorn collector:app --host 0.0.0.0 --port 8765`, workdir `workbench`,
   then `sbx_expose_port(sandbox_id, 8765, "workbench")`. If it is already running, skip this.
3. Create the sheet with the user's fields: `sbx_run_command` a `curl -s -X POST localhost:8765/sheets -H 'content-type: application/json' -d '{"name": ..., "fields": [{"key","label","type","options"}]}'`
   (field keys: letters/digits/underscore, starting with a letter). Note the returned `id`. Reuse an existing sheet
   (`GET /sheets`) if the user asked to continue one.
4. `publish_app(sandbox_id, "workbench", title, ui)`. The first argument after the sandbox is the app name the
   collector is exposed under (`workbench`), NOT the name of any other app; the sheet routes only exist there. With
   `{"kind":"sheet","title":<name>,"key":"id","rows_path":"items","list":{"method":"GET","path":"/sheets/<id>/rows"},
   "create":{"method":"POST","path":"/sheets/<id>/rows"},"update":{"method":"PUT","path":"/sheets/<id>/rows/{id}"},
   "delete":{"method":"DELETE","path":"/sheets/<id>/rows/{id}"},"columns":[<the same fields: key,label,type,options>]}`.

The user then types or pastes rows straight into the grid; they go to this app, not through you.
