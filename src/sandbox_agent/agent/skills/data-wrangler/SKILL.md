---
name: data-wrangler
description: Explore, query and chart data the user already has (DuckDB, SQLite, CSV, Parquet, JSON files in their home) and show it as tables or dashboards, without building an app. Use for "what's in this file", "summarize / compare / group", "show me a dashboard of ...".
---

# Data wrangler

The user's data lives as files in the sandbox home (the durable volume): `.duckdb`, `.db`/`.sqlite`,
`.csv`/`.tsv`, `.parquet`, `.json`/`.jsonl`. Your job is to *look at it, answer questions about it, and
render it*. You do not need to build or run an app of your own for this.

## Pick the lightest path

| The user wants | Do this |
|---|---|
| A quick answer ("how many rows", "top customers", "counts only") | Query it and reply in text (below, "Ad-hoc"). No UI. |
| To see rows or a result as a table | `show_dashboard` with one table panel. |
| Charts, KPIs, a dashboard | `show_dashboard` with several panels. |
| To *enter or edit* data | Not this skill: use the `micro-apps` skill (sheet collector). |

## 1. Find and understand the data (always first, and without writing code)

1. `sbx_list_files` on home (and subfolders) to see what data files exist.
2. Look inside a file with `show_dashboard`, not with scripts. It already has DuckDB and SQLite built in, and
   you never need `pip install` or `python` for this. Call it with one or two throwaway `table` panels:
   - `.duckdb`: `SHOW TABLES`, then `DESCRIBE <table>`, `SELECT COUNT(*) FROM <table>`, `SELECT * FROM <table> LIMIT 5`
   - `.db` / `.sqlite`: `SELECT name FROM sqlite_master WHERE type='table'`, then `PRAGMA`-free queries
     (`SELECT * FROM <table> LIMIT 5`); column names: `SELECT * FROM <table> LIMIT 0`
   - csv / parquet / json: the table is named `data`: `DESCRIBE data`, `SELECT * FROM data LIMIT 5`
3. Never write multi-line Python or heredocs to explore data: long scripted commands are the single most
   common way this agent stalls. If you truly need a script, `write_file` it first and run it with one short
   command.
4. Never modify the user's source files. They are opened read-only; write results to new files if needed.

## 2. Ad-hoc answers

Run the SQL with `sbx_run_command`, then answer in plain text with the numbers. Keep the SQL you used in
the reply so the user can check it. Aggregate in SQL; never print thousands of rows.

## 3. Dashboards and tables: `show_dashboard`

Call `show_dashboard(sandbox_id, title, panels)`. It runs each panel's SQL read-only inside the sandbox and
renders the result in the user's canvas. **No app is built, started or exposed**, and the rows never pass
through you. This is the right tool for "show me", "chart", "summarize", "dashboard".

```json
{"sandbox_id":"sbx-1a2b3c4d","title":"Sales overview","panels":[
  {"title":"Revenue","description":"Last 30 days","type":"metric","path":"sales.csv","sql":"select day, sum(amount) revenue from data group by 1 order by 1","x":"day","y":"revenue","format":"currency"},
  {"title":"Goal progress","type":"progress","path":"sales.csv","sql":"select sum(amount) v, 50000 g from data","y":"v","target":"g","format":"currency"},
  {"title":"By region","description":"Share of revenue","type":"donut","path":"sales.csv","sql":"select region, sum(amount) total from data group by 1","x":"region","y":"total","format":"currency"},
  {"title":"Daily revenue","type":"line","path":"sales.csv","sql":"select day, sum(amount) total from data group by 1 order by 1","x":"day","y":"total"},
  {"title":"Top products","type":"bar","path":"sales.csv","sql":"select product, sum(amount) t from data group by 1 order by 2 desc limit 8","x":"product","y":"t"},
  {"type":"note","title":"Worth a look","tone":"warning","text":"West is **down 18%** week over week."},
  {"title":"Latest orders","type":"table","path":"sales.csv","sql":"select * from data order by day desc limit 50"}
]}
```

Card types (pick the one that fits the question; mix them):

| `type` | Use for | Needs |
|---|---|---|
| `metric` | one headline number; if you also give `x` and several rows it draws a sparkline and shows the change vs the previous row | `y` (+ `x` for trend) |
| `progress` | a value against a goal | `y` and `target` (a column name, or a number as text) |
| `donut` | share of a total, up to ~8 slices | `x` label, `y` value |
| `bar` | ranking / comparison of categories, up to ~20 | `x` label, `y` value |
| `column` | few ordered points (months, weekdays) | `x`, `y` |
| `line` | a trend over time (area chart with hover) | `x` ordered, `y` |
| `details` | one record as key/value pairs | first row of the result |
| `table` | rows (searchable, CSV download) | any columns |
| `note` | your insight or a caveat; no query | `text` (supports `**bold**`), `tone` info/success/warning |

Every card takes an optional `description` (one line under the title). Lead with 2-4 `metric`/`progress`
cards, then the main chart(s), then a `table`; add a `note` for the one thing the user should not miss.

Panel rules:
- `path` is the data file relative to home. For csv/parquet/json files the table is named `data`; for
  `.duckdb`/`.db` files use their real table names (you profiled them in step 1).
- One read-only `SELECT`/`WITH` per panel; anything else is rejected. Files are opened read-only.
- Do the work in SQL (GROUP BY, window functions, date_trunc). Alias columns so `x`/`y`/`target` match exactly.
- 4 to 8 cards is a good dashboard. `format`: `currency`, `percent` (value 0..1), `number`, `text`.
- `wide: true` makes a card span the whole row (tables and line charts already do).

The result is a snapshot of the data at that moment. To refresh or change it, call `show_dashboard` again with
the same title. If it says a panel failed, test that SQL with `sbx_run_command` (duckdb in Python), fix it and
call again. It also answers "path not found" with the file you named: check `sbx_list_files`.

Only build an app (the `micro-apps` skill) when the user needs to *enter or edit* data or wants a live
interactive tool, not just to see their data.

## 4. When asked for insights, findings or to "dig in": do analysis, not a tour of the columns

A chart per column is not an insight. A finding is a comparison with a number in it: "Encryption at rest fails
41% of the time, about 4x the average", not "here are the counts per area".

1. Profile first, with two or three aggregate queries: the distribution of the main status, concentration (does
   one owner, product or region carry a disproportionate share?), rates by group (failure, defect, overdue rate,
   not just counts), change over time, and anything past a deadline or over a threshold.
2. Pick the three findings that are most surprising or most actionable. Compare each to the overall average or
   to the other groups, so the number means something.
3. Build the dashboard around them: for each finding, a `note` card (tone `warning` or `info`) that states it with
   the number in **bold**, then the chart that proves it. After the findings add one or two headline `metric`
   cards and a `table` of the items to act on. Compute rates in SQL (`avg(case when ... then 1.0 else 0 end)`).
4. In the reply give the three findings, one sentence each, with the numbers. Do not list the panels.

## Numbers you may quote

After `show_dashboard` you are given "Values the panels computed". Quote only those. If you need a number
that is not there, run a query for it. Never describe a figure you were not shown, and never say the data is
empty because you did not see it: a dashboard that rendered means its queries returned rows.

## What to tell the user
One or two sentences: what you found (files, row counts), what the dashboard shows, and any data quality
issue you noticed (nulls, duplicates, odd dates). Do not paste the data into the chat.
