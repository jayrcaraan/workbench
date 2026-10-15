from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from sandbox_agent.api import history
from sandbox_agent.settings import Settings

TID = "thread-12345678"


class Graph:
    checkpointer = None

    async def aget_state(self, config):
        call = {"name": "sbx_list_files", "args": {"sandbox_id": "sbx-1"}, "id": "c1"}
        return SimpleNamespace(values={
            "messages": [HumanMessage(content="hi", id="m1"), AIMessage(content="", tool_calls=[call], id="m2"),
                         ToolMessage(content="[]", tool_call_id="c1", id="m3"), AIMessage(content="done", id="m4")],
            "apps": [{"app_id": "s/a", "title": "A"}], "sandbox_id": "sbx-1"})


def make(monkeypatch, tmp_path):
    monkeypatch.setattr(history, "get_settings", lambda: Settings(_env_file=None, SANDBOX_AGENT_DATA_DIR=str(tmp_path)))
    app = FastAPI()
    app.state.graph = Graph()
    app.include_router(history.router)
    return TestClient(app)


def test_session_index_is_stored_and_updated(monkeypatch, tmp_path):
    c = make(monkeypatch, tmp_path)
    assert c.put(f"/sessions/{TID}", json={"title": "Sales dashboard", "created_at": 1000}).json()["title"] == "Sales dashboard"
    c.put(f"/sessions/{TID}", json={"sandbox_id": "sbx-0a1b2c3d"})                 # keeps the title
    row = c.get("/sessions").json()[0]
    assert row == {"id": TID, "title": "Sales dashboard", "sandboxId": "sbx-0a1b2c3d", "createdAt": 1000}
    assert c.delete(f"/sessions/{TID}").status_code == 204 and c.get("/sessions").json() == []


def test_history_returns_agui_messages_and_apps_from_the_checkpoint(monkeypatch, tmp_path):
    c = make(monkeypatch, tmp_path)
    out = c.get(f"/sessions/{TID}/history").json()
    assert [m["role"] for m in out["messages"]] == ["user", "assistant", "tool", "assistant"]
    assert out["messages"][1]["toolCalls"][0]["function"]["name"] == "sbx_list_files"
    assert out["apps"][0]["app_id"] == "s/a" and out["sandbox_id"] == "sbx-1"


def test_titles_are_short_intent_phrases_with_a_fallback():
    assert history.clean_title('"Sales dashboard".', "x y z") == "Sales dashboard"
    long = "Please could you possibly help me with something quite involved and long winded today"
    assert history.clean_title(long, "Show me revenue by region for last quarter please") == "Show me revenue by region…"
    assert history.clean_title("", "hello") == "hello"


def test_title_endpoint_names_the_session_from_the_first_message(monkeypatch, tmp_path):
    class Model:
        async def ainvoke(self, prompt):
            assert "revenue by region" in prompt
            return SimpleNamespace(content=[{"type": "text", "text": "Revenue by region"}])

    class G(Graph):
        async def aget_state(self, config):
            return SimpleNamespace(values={"messages": [HumanMessage(content="show me revenue by region", id="a")]})

    c = make(monkeypatch, tmp_path)
    c.app.state.graph = G()
    monkeypatch.setattr(history, "get_model", lambda **k: Model())
    assert c.post(f"/sessions/{TID}/title").json() == {"title": "Revenue by region"}
    assert c.get("/sessions").json()[0]["title"] == "Revenue by region"
