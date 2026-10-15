from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from sandbox_agent.agent.context import (
    OLD_ARG_CHARS,
    OLD_TOOL_RESULT_CHARS,
    trim_messages,
)


def turn(i, big="x" * 5000):
    call = {"name": "sbx_write_file", "args": {"path": f"f{i}.py", "content": big}, "id": f"c{i}"}
    return [AIMessage(content="", tool_calls=[call]), ToolMessage(content=big, tool_call_id=f"c{i}")]


def history(turns):
    msgs = [HumanMessage(content="build me an app")]
    for i in range(turns):
        msgs += turn(i)
    return msgs


def test_old_noise_is_elided_but_user_messages_and_recent_turns_are_kept():
    msgs = history(20)
    out = trim_messages(msgs, recent=6)
    assert len(out) == len(msgs) and out[0].content == "build me an app"
    old_call = out[1].tool_calls[0]["args"]
    assert len(old_call["content"]) < OLD_ARG_CHARS + 60 and old_call["path"] == "f0.py"
    assert len(out[2].content) < OLD_TOOL_RESULT_CHARS + 60
    assert out[-2].tool_calls[0]["args"]["content"] == "x" * 5000       # recent call untouched
    assert len(out[-1].content) == 5000                                  # recent result under the cap


def test_kept_window_never_starts_on_an_orphaned_tool_result():
    msgs = history(5)
    # recent=3 would start on a ToolMessage; it must pull in the AI message that called it.
    out = trim_messages(msgs, recent=3)
    assert out[-4].tool_calls and out[-4].tool_calls[0]["args"]["content"] == "x" * 5000


def test_input_is_not_mutated_and_small_histories_are_unchanged():
    msgs = history(2)
    before = msgs[1].tool_calls[0]["args"]["content"]
    trim_messages(msgs, recent=2)
    assert msgs[1].tool_calls[0]["args"]["content"] == before
    small = [HumanMessage(content="hi"), AIMessage(content="hello")]
    assert trim_messages(small) == small
