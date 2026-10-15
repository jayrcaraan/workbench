import os
import sqlite3
import subprocess
import sys

import duckdb

from sandbox_agent import sandbox
from sandbox_agent.apps import data
from sandbox_agent.apps.spec import Panel


class Runtime:
    tool_call_id = "call-1"


def local_sandbox(home, monkeypatch):
    """Executes the runner for real, against files in `home`, instead of inside a sandbox."""
    async def call(tool, **args):
        assert tool == "run_command"
        done = subprocess.run(["bash", "-c", args["command"].replace("python3", sys.executable, 1)],
                              capture_output=True, text=True, env={**os.environ, "HOME": str(home)})
        return {"stdout": done.stdout, "stderr": done.stderr, "returncode": done.returncode}

    async def access(sid, fresh=False):
        return {"token": "t", "apps": []} if sid == "sbx-1" else None

    monkeypatch.setattr(sandbox, "call", call)
    monkeypatch.setattr(sandbox, "access", access)


def fixtures(home):
    (home / "sales.csv").write_text("region,amount,day\nEU,10,2026-01-01\nUS,25,2026-01-02\nEU,5,2026-01-03\n")
    s = sqlite3.connect(home / "app.db")
    s.execute("create table t(a int, b text)")
    s.executemany("insert into t values (?,?)", [(1, "x"), (2, "y")])
    s.commit()
    s.close()
    d = duckdb.connect(str(home / "wh.duckdb"))
    d.execute("create table orders as select range as id, range*2 as total from range(5)")
    d.close()


async def test_queries_run_read_only_over_csv_sqlite_and_duckdb(tmp_path, monkeypatch):
    local_sandbox(tmp_path, monkeypatch)
    fixtures(tmp_path)
    csv = await data.run_query("sbx-1", "sales.csv", "select region, sum(amount) total from data group by 1 order by 1")
    assert csv.columns == ["region", "total"] and csv.rows == [["EU", 15], ["US", 25]]
    assert (await data.run_query("sbx-1", "app.db", "select * from t order by a")).rows == [[1, "x"], [2, "y"]]
    assert (await data.run_query("sbx-1", "wh.duckdb", "select count(*) from orders")).rows == [[5]]
    for bad in ["drop table t", "select 1; drop table t", "insert into t values (3,'z')", "attach 'x'"]:
        assert (await data.run_query("sbx-1", "app.db", bad)).error, bad
    assert "inside the home" in (await data.run_query("sbx-1", "../etc/passwd", "select 1")).error
    cut = await data.run_query("sbx-1", "sales.csv", "select * from data", limit=2)
    assert cut.truncated and len(cut.rows) == 2


async def test_show_dashboard_puts_results_in_state_without_an_app(tmp_path, monkeypatch):
    local_sandbox(tmp_path, monkeypatch)
    fixtures(tmp_path)
    panels = [
        Panel(title="Total", type="metric", path="sales.csv", sql="select sum(amount) t from data", y="t"),
        Panel(title="By region", type="bar", path="sales.csv", sql="select region, sum(amount) t from data group by 1", x="region", y="t"),
        Panel(title="Broken", path="sales.csv", sql="select nope from data"),
    ]
    cmd = await data.show_dashboard.coroutine(sandbox_id="sbx-1", title="Sales", panels=panels, runtime=Runtime())
    app = cmd.update["apps"][0]
    assert app["app_id"] == "sbx-1/dashboard-sales" and app["ui"]["kind"] == "dashboard"
    assert app["ui"]["panels"][0]["result"]["rows"] == [[40]]
    assert app["ui"]["panels"][2]["result"]["error"]
    assert "Panels with problems" in cmd.update["messages"][0].content


async def test_show_dashboard_refuses_when_every_panel_fails_or_sandbox_missing(tmp_path, monkeypatch):
    local_sandbox(tmp_path, monkeypatch)
    only_bad = [Panel(title="x", path="missing.csv", sql="select 1")]
    cmd = await data.show_dashboard.coroutine(sandbox_id="sbx-1", title="T", panels=only_bad, runtime=Runtime())
    assert "apps" not in cmd.update and "every panel failed" in cmd.update["messages"][0].content
    cmd = await data.show_dashboard.coroutine(sandbox_id="sbx-9", title="T", panels=only_bad, runtime=Runtime())
    assert "does not exist" in cmd.update["messages"][0].content


async def test_note_cards_need_no_query_and_new_card_types_validate(tmp_path, monkeypatch):
    import pytest
    from pydantic import ValidationError

    local_sandbox(tmp_path, monkeypatch)
    fixtures(tmp_path)
    cards = [
        Panel(title="Heads up", type="note", text="Revenue is **up**", tone="success"),
        Panel(title="Share", type="donut", path="sales.csv", sql="select region, sum(amount) t from data group by 1", x="region", y="t"),
        Panel(title="Goal", type="progress", path="sales.csv", sql="select sum(amount) v, 100 g from data", y="v", target="g"),
        Panel(title="Record", type="details", path="app.db", sql="select * from t limit 1"),
    ]
    cmd = await data.show_dashboard.coroutine(sandbox_id="sbx-1", title="Mix", panels=cards, runtime=Runtime())
    ui = cmd.update["apps"][0]["ui"]
    assert ui["panels"][0].get("result") is None and ui["panels"][1]["result"]["rows"]
    assert ui["panels"][2]["result"]["rows"] == [[40, 100]]
    with pytest.raises(ValidationError):
        Panel(title="x", type="bar")                       # data cards need path + sql
    with pytest.raises(ValidationError):
        Panel(title="x", type="note")                      # notes need text


async def test_a_wrong_file_name_lists_the_data_files_that_exist(tmp_path, monkeypatch):
    local_sandbox(tmp_path, monkeypatch)
    fixtures(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "control-tracker.db").write_bytes(b"x")
    res = await data.run_query("sbx-1", "data/control_testing_tracker.db", "select 1")
    assert "no such file" in res.error and "data/control-tracker.db" in res.error and "sales.csv" in res.error


async def test_panels_may_arrive_as_a_json_string(tmp_path, monkeypatch):
    import json

    local_sandbox(tmp_path, monkeypatch)
    fixtures(tmp_path)
    as_text = json.dumps([{"title": "Total", "type": "metric", "path": "sales.csv", "sql": "select sum(amount) t from data", "y": "t"}])
    cmd = await data.show_dashboard.coroutine(sandbox_id="sbx-1", title="Sales", panels=as_text, runtime=Runtime())
    assert cmd.update["apps"][0]["ui"]["panels"][0]["result"]["rows"] == [[40]]
    bad = await data.show_dashboard.coroutine(sandbox_id="sbx-1", title="Sales", panels="not json", runtime=Runtime())
    assert "must be a list" in bad.update["messages"][0].content


async def test_the_model_is_told_the_aggregates_it_put_on_screen_but_not_table_rows(tmp_path, monkeypatch):
    local_sandbox(tmp_path, monkeypatch)
    fixtures(tmp_path)
    panels = [
        Panel(title="Total", type="metric", path="sales.csv", sql="select sum(amount) t from data", y="t"),
        Panel(title="By region", type="bar", path="sales.csv", sql="select region, sum(amount) t from data group by 1 order by 1", x="region", y="t"),
        Panel(title="Everything", type="table", path="sales.csv", sql="select * from data"),
    ]
    cmd = await data.show_dashboard.coroutine(sandbox_id="sbx-1", title="Sales", panels=panels, runtime=Runtime())
    text = cmd.update["messages"][0].content
    assert "Total: columns ['t'], rows [[40]]" in text
    assert "By region" in text and "['EU', 15]" in text and "['US', 25]" in text
    assert "Everything: 3 row(s)" in text and "2026-01-02" not in text      # row-level data stays out
