import importlib.util
import json
import subprocess
import sys
import time

from fastapi.testclient import TestClient

from sandbox_agent.agent.tools import REFERENCES


def load(name, home):
    spec = importlib.util.spec_from_file_location(name, REFERENCES / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _template(tmp_path, monkeypatch, fields=None, title="items"):
    monkeypatch.setenv("HOME", str(tmp_path))
    app_dir = tmp_path / "app"
    app_dir.mkdir(exist_ok=True)
    src = (REFERENCES / "app-template.py").read_text()
    (app_dir / "main.py").write_text(src)
    if fields is not None:
        (app_dir / "fields.json").write_text(json.dumps({"title": title, "fields": fields}))
    spec = importlib.util.spec_from_file_location("tpl_main", app_dir / "main.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_app_template_runs_and_follows_the_conventions(tmp_path, monkeypatch):
    c = TestClient(_template(tmp_path, monkeypatch).app)
    assert c.get("/health").json() == {"status": "ok"}
    made = c.post("/items", json={"items": [{"name": "bolt", "quantity": "12"}, {"name": "nut"}]}).json()["items"]
    assert made[0]["quantity"] == 12 and made[1]["quantity"] is None
    assert c.put(f"/items/{made[1]['id']}", json={"quantity": 3}).json()["quantity"] == 3
    assert [r["name"] for r in c.get("/items").json()["items"]] == ["bolt", "nut"]
    assert c.post("/items", json={"quantity": "lots"}).status_code == 422
    assert c.delete(f"/items/{made[0]['id']}").status_code == 204
    assert (tmp_path / "data" / "items.db").is_file()


def test_app_template_is_configured_by_fields_json_and_documents_every_field(tmp_path, monkeypatch):
    fields = [
        {"key": "item", "label": "Item", "type": "text"},
        {"key": "packed", "label": "Packed", "type": "checkbox"},
        {"key": "due", "label": "Due", "type": "date"},
        {"key": "tier", "label": "Tier", "type": "select", "options": ["a", "b"]},
    ]
    c = TestClient(_template(tmp_path, monkeypatch, fields, "Trip Checklist").app)
    props = c.get("/openapi.json").json()["components"]["schemas"]["Item"]["properties"]
    assert {"id", "item", "packed", "due", "tier"} <= set(props)       # not an opaque `additionalProp1`
    assert props["tier"]["enum"] == ["a", "b"] and props["due"]["format"] == "date"
    row = c.post("/items", json={"item": "Passport", "packed": "yes", "due": "2026-10-20", "tier": "a"}).json()["items"][0]
    assert row["packed"] is True
    assert c.post("/items", json={"tier": "zzz"}).status_code == 422
    assert (tmp_path / "data" / "trip_checklist.db").is_file()


def test_app_template_stores_typed_columns_and_adds_new_ones(tmp_path, monkeypatch):
    import sqlite3

    first = [{"key": "name", "label": "Name", "type": "text"}, {"key": "quantity", "label": "Qty", "type": "number"}]
    c = TestClient(_template(tmp_path, monkeypatch, first).app)
    c.post("/items", json={"name": "bolt", "quantity": 4})
    db = tmp_path / "data" / "items.db"
    assert {r[1]: r[2] for r in sqlite3.connect(db).execute("PRAGMA table_info(items)")} == {
        "id": "INTEGER", "name": "TEXT", "quantity": "REAL"}
    c = TestClient(_template(tmp_path, monkeypatch, first + [{"key": "colour", "label": "Colour", "type": "text"}]).app)
    assert c.get("/items").json()["items"][0]["colour"] is None            # new column, old row kept
    assert "colour" in {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(items)")}


def test_sql_helper_prints_tables_and_schema(tmp_path):
    import sqlite3

    db = tmp_path / "x.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
    con.execute("INSERT INTO items (name) VALUES ('bolt')")
    con.commit()
    run = lambda *a: subprocess.run([sys.executable, str(REFERENCES / "sql.py"), str(db), *a], capture_output=True, text=True, check=False)
    assert "bolt" in run("SELECT * FROM items").stdout and "(1 rows)" in run("SELECT * FROM items").stdout
    assert "CREATE TABLE items" in run(".schema").stdout and run(".tables").stdout.strip() == "items"


def test_smoke_script_reports_ok_and_failures():
    server = subprocess.Popen([sys.executable, "-m", "http.server", "18765", "--bind", "127.0.0.1"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(1)
        ok = subprocess.run([sys.executable, str(REFERENCES / "smoke.py"), "18765", "/"], capture_output=True, text=True)
        assert ok.returncode == 0 and "ok" in ok.stdout
        bad = subprocess.run([sys.executable, str(REFERENCES / "smoke.py"), "18765", "/nope"], capture_output=True, text=True)
        assert bad.returncode == 1 and "FAIL 404" in bad.stdout
    finally:
        server.terminate()
