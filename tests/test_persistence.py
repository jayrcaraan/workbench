from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from sandbox_agent.apps import AppsState


async def test_thread_state_survives_a_new_process(tmp_path):
    """Same sqlite file, a brand-new saver and graph: the thread's messages and custom state are still there."""
    db = str(tmp_path / "threads.sqlite")
    cfg = {"configurable": {"thread_id": "t1"}}

    async def graph(saver):
        model = GenericFakeChatModel(messages=iter([AIMessage(content="hello back")]))
        return create_agent(model, tools=[], state_schema=AppsState, checkpointer=saver)

    async with AsyncSqliteSaver.from_conn_string(db) as saver:
        g = await graph(saver)
        await g.ainvoke({"messages": [("user", "hi")], "apps": [{"app_id": "s/a", "title": "A"}], "sandbox_id": "sbx-1"}, cfg)

    async with AsyncSqliteSaver.from_conn_string(db) as saver:     # "after a restart"
        state = (await (await graph(saver)).aget_state(cfg)).values
    assert [m.content for m in state["messages"]] == ["hi", "hello back"]
    assert state["sandbox_id"] == "sbx-1" and state["apps"][0]["app_id"] == "s/a"
