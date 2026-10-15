import pytest
from fastapi.testclient import TestClient

FIELDS = [
    {"key": "name", "label": "Name", "type": "text"},
    {"key": "amount", "label": "Amount", "type": "currency"},
    {"key": "day", "label": "Day", "type": "date"},
    {"key": "tier", "label": "Tier", "type": "select", "options": ["free", "pro"]},
    {"key": "paid", "label": "Paid", "type": "checkbox"},
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKBENCH_DB", str(tmp_path / "home" / "workbench.db"))
    import importlib.util

    from sandbox_agent.agent.tools import REFERENCES

    SOURCE = REFERENCES / "sheet-collector.py"

    spec = importlib.util.spec_from_file_location("sheet_collector", SOURCE)
    collector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(collector)
    return TestClient(collector.app), tmp_path


def test_sheet_and_row_lifecycle_is_typed_and_persistent(client):
    c, tmp = client
    sid = c.post("/sheets", json={"name": "Orders", "fields": FIELDS}).json()["id"]
    created = c.post(f"/sheets/{sid}/rows", json={"items": [
        {"name": "Ada", "amount": "$1,240.50", "day": "2026-10-02", "tier": "pro", "paid": "yes"},
        {"name": "Grace", "amount": 15},
    ]}).json()["items"]
    assert created[0]["amount"] == 1240.5 and created[0]["paid"] is True
    assert created[1]["tier"] is None and created[1]["paid"] is False

    rid = created[1]["id"]
    assert c.put(f"/sheets/{sid}/rows/{rid}", json={"tier": "free"}).json()["tier"] == "free"
    assert [r["name"] for r in c.get(f"/sheets/{sid}/rows").json()["items"]] == ["Ada", "Grace"]
    assert c.get("/sheets").json()["items"][0]["rows"] == 2
    assert c.delete(f"/sheets/{sid}/rows/{rid}").status_code == 204
    assert len(c.get(f"/sheets/{sid}/rows").json()["items"]) == 1
    assert (tmp / "home" / "workbench.db").is_file()   # lives in the (home) volume, not in memory


def test_invalid_values_are_rejected_and_batch_is_all_or_nothing(client):
    c, _ = client
    sid = c.post("/sheets", json={"name": "S", "fields": FIELDS}).json()["id"]
    bad = c.post(f"/sheets/{sid}/rows", json={"items": [{"name": "ok"}, {"amount": "abc"}]})
    assert bad.status_code == 422 and "Amount" in bad.json()["detail"]
    assert c.get(f"/sheets/{sid}/rows").json()["items"] == []
    assert c.post(f"/sheets/{sid}/rows", json={"tier": "gold"}).status_code == 422
    assert c.post(f"/sheets/{sid}/rows", json={"day": "10/02/2026"}).status_code == 422


def test_schema_validation_and_delete(client):
    c, _ = client
    assert c.post("/sheets", json={"name": "x", "fields": [{"key": "1a", "label": "A"}]}).status_code == 422
    dup = [{"key": "a", "label": "A"}, {"key": "a", "label": "B"}]
    assert c.post("/sheets", json={"name": "x", "fields": dup}).status_code == 422
    sid = c.post("/sheets", json={"name": "x", "fields": FIELDS}).json()["id"]
    assert c.delete(f"/sheets/{sid}").status_code == 204
    assert c.get(f"/sheets/{sid}").status_code == 404


def test_rows_are_real_typed_columns_not_json_blobs(client):
    import sqlite3

    c, tmp = client
    sid = c.post("/sheets", json={"name": "Orders", "fields": FIELDS}).json()["id"]
    c.post(f"/sheets/{sid}/rows", json={"name": "Ada", "amount": "12.5", "day": "2026-10-02", "tier": "pro", "paid": True})
    con = sqlite3.connect(tmp / "home" / "workbench.db")
    cols = {r[1]: r[2] for r in con.execute(f'PRAGMA table_info("sheet_{sid}")')}
    assert cols == {"id": "INTEGER", "name": "TEXT", "amount": "REAL", "day": "TEXT", "tier": "TEXT", "paid": "INTEGER"}
    # plain SQL works, which a JSON blob would not allow
    assert con.execute(f'SELECT sum(amount) FROM "sheet_{sid}" WHERE paid = 1').fetchone()[0] == 12.5


def test_new_fields_become_columns_and_old_blob_rows_are_imported(client):
    import json
    import sqlite3

    c, tmp = client
    db = tmp / "home" / "workbench.db"
    c.get("/sheets")  # creates the schema
    con = sqlite3.connect(db)
    con.executescript('CREATE TABLE rows (id INTEGER PRIMARY KEY AUTOINCREMENT, sheet_id TEXT NOT NULL, data TEXT NOT NULL);')
    con.execute("INSERT INTO sheets (id, name, fields) VALUES (?,?,?)", ("legacy1", "Old", json.dumps(FIELDS)))
    con.execute("INSERT INTO rows (sheet_id, data) VALUES (?,?)", ("legacy1", json.dumps({"name": "Ada", "paid": True})))
    con.commit()
    con.close()
    assert [r["name"] for r in c.get("/sheets/legacy1/rows").json()["items"]] == ["Ada"]

    extra = FIELDS + [{"key": "note", "label": "Note", "type": "text"}]
    assert c.put("/sheets/legacy1", json={"name": "Old", "fields": extra}).status_code == 200
    row = c.get("/sheets/legacy1/rows").json()["items"][0]
    assert row["name"] == "Ada" and row["paid"] is True and row["note"] is None
