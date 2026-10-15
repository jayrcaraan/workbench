from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from sandbox_agent.llm import DatabricksChatModel


def model():
    return DatabricksChatModel(base_url="http://x/v1", api_key="k", model="m")


def test_request_payload_flattens_text_block_lists():
    msgs = [
        HumanMessage(content="hi"),
        AIMessage(content=[""], tool_calls=[{"name": "f", "args": {}, "id": "c1"}]),
        ToolMessage(content=[{"type": "text", "text": "a"}, {"type": "text", "text": "b"}], tool_call_id="c1"),
    ]
    payload = model()._get_request_payload(msgs)
    contents = [m.get("content") for m in payload["messages"]]
    assert all(c is None or isinstance(c, str) for c in contents)
    assert contents[-1] == "ab"


def test_request_payload_drops_reasoning_blocks_from_replayed_messages():
    msgs = [
        HumanMessage(content="hi"),
        AIMessage(content=[{"type": "reasoning", "summary": [{"text": "thinking"}]},
                           {"type": "text", "text": "hello"}]),
    ]
    contents = [m["content"] for m in model()._get_request_payload(msgs)["messages"]]
    assert contents == ["hi", "hello"]


def test_reasoning_blocks_are_left_in_responses_for_the_ui():
    # Nothing in the adapter rewrites responses any more: block lists reach ag-ui-langgraph intact.
    assert not hasattr(DatabricksChatModel, "_create_chat_result") or \
        DatabricksChatModel._create_chat_result.__qualname__.startswith("BaseChatOpenAI")
