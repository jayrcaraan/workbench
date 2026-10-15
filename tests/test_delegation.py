import asyncio
from types import SimpleNamespace

from langchain.agents.middleware import ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from sandbox_agent.agent.delegation import (
    EMPTY_REPORT,
    PUBLISH_NUDGE,
    guard_task,
    require_publish_after_delegation,
)


def task_call(i=1):
    return AIMessage(content="", tool_calls=[{"name": "task", "args": {"description": "build"}, "id": f"t{i}"}])


async def test_empty_subagent_report_is_not_treated_as_success():
    async def handler(req):
        return ToolMessage(content="  ", tool_call_id="t1", name="task")

    req = SimpleNamespace(tool_call={"name": "task", "args": {"description": "x"}, "id": "t1"}, state={})
    out = await guard_task.awrap_tool_call(req, handler)
    assert out.content == EMPTY_REPORT and out.status == "error"


async def test_identical_parallel_task_calls_run_once():
    ran = []

    async def handler(req):
        ran.append(1)
        await asyncio.sleep(0.05)
        return ToolMessage(content="report", tool_call_id=req.tool_call["id"], name="task")

    state = {}
    def req(i):
        return SimpleNamespace(tool_call={"name": "task", "args": {"description": "same"}, "id": f"t{i}"}, state=state)

    outs = await asyncio.gather(guard_task.awrap_tool_call(req(1), handler), guard_task.awrap_tool_call(req(2), handler))
    assert len(ran) == 1 and sorted(o.content for o in outs) == sorted(["report", outs[0].content if outs[0].content != "report" else outs[1].content])
    assert any(o.status == "error" for o in outs if getattr(o, "status", None))


class Req:
    def __init__(self, messages):
        self.messages = messages

    def override(self, **kw):
        return Req(kw.get("messages", self.messages))


async def run_guard(messages, answers):
    seen = []

    async def handler(req):
        seen.append(list(req.messages))
        return ModelResponse(result=[answers.pop(0)])

    out = await require_publish_after_delegation.awrap_model_call(Req(messages), handler)
    return out, seen


async def test_claiming_done_after_delegating_without_publishing_is_challenged_once():
    msgs = [HumanMessage(content="build"), task_call(), ToolMessage(content="report", tool_call_id="t1", name="task")]
    out, seen = await run_guard(msgs, [AIMessage(content="It is ready!"), AIMessage(content="", tool_calls=[
        {"name": "publish_app", "args": {}, "id": "p1"}])])
    assert len(seen) == 2 and seen[1][-1].content == PUBLISH_NUDGE
    assert out.result[-1].tool_calls


async def test_no_nudge_after_publish_or_without_delegation():
    pub = [HumanMessage(content="build"), task_call(), ToolMessage(content="r", tool_call_id="t1", name="task"),
           AIMessage(content="", tool_calls=[{"name": "publish_app", "args": {}, "id": "p"}]),
           ToolMessage(content="Published 'X' (s/x)", tool_call_id="p")]
    _, seen = await run_guard(pub, [AIMessage(content="done")])
    assert len(seen) == 1
    _, seen = await run_guard([HumanMessage(content="hi")], [AIMessage(content="hello")])
    assert len(seen) == 1
