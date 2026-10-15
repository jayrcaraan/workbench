import json
from types import SimpleNamespace

from langchain_core.messages import ToolMessage
from langgraph.types import Command

from sandbox_agent import sandbox
from sandbox_agent.agent import session
from sandbox_agent.agent.session import one_sandbox_per_session


def request(state):
    return SimpleNamespace(tool_call={"name": "sbx_create_sandbox", "args": {}, "id": "c1"}, state=state)


async def test_first_create_records_the_sandbox_in_state():
    async def handler(req):
        return ToolMessage(content=json.dumps({"sandbox_id": "sbx-0a1b2c3d", "status": "ready"}), tool_call_id="c1")

    out = await one_sandbox_per_session.awrap_tool_call(request({}), handler)
    assert isinstance(out, Command) and out.update["sandbox_id"] == "sbx-0a1b2c3d"
    assert out.update["messages"][0].tool_call_id == "c1"


async def test_second_create_in_the_session_returns_the_same_sandbox(monkeypatch):
    async def access(sid, fresh=False):
        return {"token": "t", "apps": []}

    monkeypatch.setattr(sandbox, "access", access)

    async def handler(req):
        raise AssertionError("must not provision another sandbox")

    out = await one_sandbox_per_session.awrap_tool_call(request({"sandbox_id": "sbx-0a1b2c3d"}), handler)
    assert json.loads(out.content) == {
        "status": "reused", "sandbox_id": "sbx-0a1b2c3d",
        "note": "This session already has a sandbox. Use it; do not create another.",
    }


async def test_a_reaped_sandbox_is_replaced(monkeypatch):
    async def access(sid, fresh=False):
        return None

    monkeypatch.setattr(sandbox, "access", access)

    async def handler(req):
        return ToolMessage(content='{"sandbox_id": "sbx-ffffffff"}', tool_call_id="c1")

    out = await one_sandbox_per_session.awrap_tool_call(request({"sandbox_id": "sbx-0a1b2c3d"}), handler)
    assert out.update["sandbox_id"] == "sbx-ffffffff"


async def test_other_tools_pass_through():
    async def handler(req):
        return "ran"

    req = SimpleNamespace(tool_call={"name": "sbx_run_command", "args": {}, "id": "c2"}, state={})
    assert await one_sandbox_per_session.awrap_tool_call(req, handler) == "ran"


async def test_parallel_creates_in_one_session_provision_exactly_one(monkeypatch):
    import asyncio

    session._known.clear()
    created = []

    async def access(sid, fresh=False):
        return {"token": "t", "apps": []}

    monkeypatch.setattr(sandbox, "access", access)

    async def handler(req):
        await asyncio.sleep(0.05)
        created.append(1)
        return ToolMessage(content=f'{{"sandbox_id": "sbx-{len(created):08x}"}}', tool_call_id=req.tool_call["id"])

    outs = await asyncio.gather(*(one_sandbox_per_session.awrap_tool_call(request({}), handler) for _ in range(3)))
    assert len(created) == 1
    ids = {o.update["sandbox_id"] for o in outs}
    assert ids == {"sbx-00000001"}
