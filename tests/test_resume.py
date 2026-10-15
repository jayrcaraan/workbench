from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from sandbox_agent import sandbox
from sandbox_agent.agent import session as guard
from sandbox_agent.api import sessions
from sandbox_agent.apps.publish import build_recipe, merge_apps

TID = "thread-12345678"


def call(name, args, i):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c{i}"}])


MSGS = [
    call("sbx_run_command", {"sandbox_id": "sbx-1", "command": "pip install -q duckdb"}, 1),
    call("sbx_run_command", {"sandbox_id": "sbx-1", "command": "ls"}, 2),
    call("sbx_start_background", {"sandbox_id": "sbx-1", "command": "python -m http.server 9000", "workdir": "other"}, 3),
    call("sbx_start_background", {"sandbox_id": "sbx-1", "command": "uvicorn main:app --port 8000", "workdir": "tasks", "log_file": "t.log"}, 4),
    call("sbx_expose_port", {"sandbox_id": "sbx-1", "internal_port": 8000, "name": "tasks"}, 5),
]


def test_recipe_picks_the_start_command_for_the_exposed_port_and_replays_installs():
    r = build_recipe(MSGS, "tasks")
    assert r == {"name": "tasks", "port": 8000, "setup": ["pip install -q duckdb"],
                 "start": {"command": "uvicorn main:app --port 8000", "workdir": "tasks", "log_file": "t.log"}}
    assert build_recipe(MSGS, "other") is None            # never exposed under that name


def test_resumed_app_replaces_the_old_entry():
    old = [{"app_id": "sbx-1/tasks", "title": "T"}, {"app_id": "sbx-1/x", "title": "X"}]
    out = merge_apps(old, [{"app_id": "sbx-2/tasks", "title": "T", "replaces": "sbx-1/tasks"}])
    assert [a["app_id"] for a in out] == ["sbx-1/x", "sbx-2/tasks"] and "replaces" not in out[1]


class Graph:
    def __init__(self):
        app = {"app_id": "sbx-dead0001/tasks", "name": "tasks", "title": "Task Tracker",
               "ui": {"kind": "sheet", "title": "T", "key": "id", "list": {"path": "/tasks"}, "columns": []},
               "recipe": build_recipe(MSGS, "tasks")}
        self.values = {"apps": [app]}
        self.updates = []

    async def aget_state(self, config):
        return SimpleNamespace(values=self.values)

    async def aupdate_state(self, config, values):
        self.updates.append(values)


def test_resume_restarts_the_app_in_a_new_sandbox(monkeypatch):
    calls = []

    async def scall(tool, **args):
        calls.append((tool, args))
        return {"sandbox_id": "sbx-aaaaaaaa"} if tool == "create_sandbox" else {}

    async def access(sid, fresh=False):
        if sid == "sbx-dead0001":
            return None
        return {"token": "t", "apps": [{"name": "tasks", "port": 8000, "url": "http://tasks.sbx-aaaaaaaa.sandbox.localhost"}]}

    async def ok_probe(url, token, *a, **k):
        return None

    monkeypatch.setattr(sandbox, "call", scall)
    monkeypatch.setattr(sandbox, "access", access)
    import sandbox_agent.apps.publish as pub
    monkeypatch.setattr(pub, "probe", ok_probe)
    guard._known.clear(); guard._locks.clear()
    app = FastAPI(); g = Graph(); app.state.graph = g; app.include_router(sessions.router)
    out = TestClient(app).post(f"/sessions/{TID}/apps/tasks/resume").json()
    assert out["app"]["app_id"] == "sbx-aaaaaaaa/tasks" and out["replaces"] == "sbx-dead0001/tasks"
    assert [c[0] for c in calls] == ["create_sandbox", "run_command", "start_background", "expose_port"]
    assert calls[2][1]["command"] == "uvicorn main:app --port 8000" and calls[3][1]["internal_port"] == 8000
    assert g.updates[-1]["apps"][0]["replaces"] == "sbx-dead0001/tasks"
