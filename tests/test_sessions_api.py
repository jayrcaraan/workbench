from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sandbox_agent import sandbox
from sandbox_agent.agent import session as guard
from sandbox_agent.api import sessions

TID = "thread-12345678"


class FakeGraph:
    def __init__(self, sandbox_id=None):
        self.values = {"sandbox_id": sandbox_id} if sandbox_id else {}
        self.updates = []

    async def aget_state(self, config):
        return SimpleNamespace(values=self.values)

    async def aupdate_state(self, config, values):
        self.updates.append(values)
        self.values.update(values)


def client(monkeypatch, graph, alive=("sbx-0a1b2c3d",)):
    created = []

    async def call(tool, **args):
        assert tool == "create_sandbox"
        created.append(args)
        return {"sandbox_id": "sbx-aaaaaaaa"}

    async def access(sid, fresh=False):
        return {"token": "t", "apps": []} if sid in alive or sid == "sbx-aaaaaaaa" else None

    monkeypatch.setattr(sandbox, "call", call)
    monkeypatch.setattr(sandbox, "access", access)
    guard._known.clear()
    guard._locks.clear()
    app = FastAPI()
    app.state.graph = graph
    app.include_router(sessions.router)
    return TestClient(app), created


def test_starts_a_sandbox_and_records_it_in_the_thread_state(monkeypatch):
    g = FakeGraph()
    c, created = client(monkeypatch, g)
    out = c.post(f"/sessions/{TID}/sandbox").json()
    assert out == {"sandbox_id": "sbx-aaaaaaaa", "state": "ready", "created": True}
    assert g.updates == [{"sandbox_id": "sbx-aaaaaaaa"}] and len(created) == 1
    again = c.post(f"/sessions/{TID}/sandbox").json()          # idempotent
    assert again["created"] is False and len(created) == 1
    assert c.get(f"/sessions/{TID}/sandbox").json()["sandbox_id"] == "sbx-aaaaaaaa"


def test_reuses_a_live_sandbox_and_replaces_a_reaped_one(monkeypatch):
    c, created = client(monkeypatch, FakeGraph("sbx-0a1b2c3d"))
    assert c.post(f"/sessions/{TID}/sandbox").json()["sandbox_id"] == "sbx-0a1b2c3d" and not created
    c, created = client(monkeypatch, FakeGraph("sbx-deadbeef"))   # not alive any more
    assert c.post(f"/sessions/{TID}/sandbox").json()["created"] is True and len(created) == 1


def test_rejects_bad_thread_ids(monkeypatch):
    c, _ = client(monkeypatch, FakeGraph())
    assert c.post("/sessions/..%2Fx/sandbox").status_code in (400, 404)
