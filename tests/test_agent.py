import pytest
from langchain.agents.middleware import ModelResponse
from langchain_core.messages import AIMessage, HumanMessage

from sandbox_agent.agent import SKILLS_DIR
from sandbox_agent.agent.retry import GIVE_UP, NUDGE, STEER, _is_empty, retry_empty_turn


class Req:
    def __init__(self, messages):
        self.messages = messages

    def override(self, **kw):
        return Req(kw.get("messages", self.messages))


def resp(content="", tool_calls=None):
    return ModelResponse(result=[AIMessage(content=content, tool_calls=tool_calls or [])])


def empty(r):
    return _is_empty(r.result[-1])


def test_is_empty_turn():
    assert empty(resp(""))
    assert empty(resp("   "))
    assert empty(resp([{"type": "text", "text": ""}]))
    assert not empty(resp("hi"))
    assert not empty(resp("", [{"name": "f", "args": {}, "id": "1"}]))


@pytest.mark.asyncio
async def test_retries_empty_turn_then_returns_answer():
    seen = []
    answers = [resp(""), resp("done")]

    async def handler(req):
        seen.append([m.content for m in req.messages])
        return answers.pop(0)

    out = await retry_empty_turn.awrap_model_call(Req([HumanMessage(content="q")]), handler)
    assert out.result[-1].content == "done"
    assert seen[1][-1] == NUDGE


class ToolReq(Req):
    def __init__(self, messages, tools=("t",), tool_choice=None):
        super().__init__(messages)
        self.tools, self.tool_choice = list(tools), tool_choice

    def override(self, **kw):
        return ToolReq(kw.get("messages", self.messages), self.tools, kw.get("tool_choice", self.tool_choice))


@pytest.mark.asyncio
async def test_escalates_to_a_forced_tool_call_then_recovers():
    choices = []
    answers = [resp(""), resp(""), resp("", [{"name": "f", "args": {}, "id": "1"}])]
    last_msgs = []

    async def handler(req):
        choices.append(req.tool_choice)
        last_msgs.append(req.messages[-1].content if req.messages else None)
        return answers.pop(0)

    out = await retry_empty_turn.awrap_model_call(ToolReq([HumanMessage(content="q")]), handler)
    assert out.result[-1].tool_calls
    assert choices == [None, None, "required"]   # nudge first, forced from the second retry
    assert last_msgs[1] == NUDGE and last_msgs[2] == STEER   # generic first, concrete from the second retry


@pytest.mark.asyncio
async def test_says_so_in_the_chat_when_the_model_stays_empty():
    calls = {"n": 0}

    async def always_empty(req):
        calls["n"] += 1
        return resp("")

    out = await retry_empty_turn.awrap_model_call(ToolReq([]), always_empty)
    assert calls["n"] == 1 + 3                      # first try + three retries
    assert out.result[-1].content == GIVE_UP and not _is_empty(out.result[-1])

    calls["n"] = 0

    async def good(req):
        calls["n"] += 1
        return resp("fine")

    await retry_empty_turn.awrap_model_call(Req([]), good)
    assert calls["n"] == 1


def test_micro_apps_skill_is_packaged_with_frontmatter():
    text = (SKILLS_DIR / "micro-apps" / "SKILL.md").read_text()
    assert text.startswith("---\nname: micro-apps\n")
    assert "description:" in text.split("---")[1]
