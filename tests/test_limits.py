from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from sandbox_agent.agent.limits import refuse_repeats


def call(i, cmd="curl localhost:8000/health"):
    return AIMessage(content="", tool_calls=[{"name": "sbx_run_command", "args": {"command": cmd}, "id": f"c{i}"}])


def result(i, text):
    return ToolMessage(content=text, tool_call_id=f"c{i}")


async def run(messages, cmd="curl localhost:8000/health"):
    ran = []

    async def handler(req):
        ran.append(req)
        return ToolMessage(content="executed", tool_call_id="new")

    req = SimpleNamespace(
        tool_call={"name": "sbx_run_command", "args": {"command": cmd}, "id": "new"},
        state={"messages": messages},
    )
    out = await refuse_repeats.awrap_tool_call(req, handler)
    return out, ran


async def test_third_identical_call_with_identical_result_is_refused():
    msgs = [HumanMessage(content="go"), call(1), result(1, "000"), call(2), result(2, "000")]
    out, ran = await run(msgs)
    assert not ran and out.status == "error" and "exact call 2 times" in out.content


async def test_repeat_is_allowed_when_results_differ_or_args_differ():
    msgs = [HumanMessage(content="go"), call(1), result(1, "000"), call(2), result(2, "200")]
    out, ran = await run(msgs)
    assert ran and out.content == "executed"
    out, ran = await run([call(1), result(1, "000"), call(2), result(2, "000")], cmd="curl localhost:9000")
    assert ran


async def test_first_and_second_calls_pass():
    out, ran = await run([HumanMessage(content="go"), call(1), result(1, "000")])
    assert ran
