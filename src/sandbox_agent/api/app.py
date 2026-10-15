"""FastAPI service: AG-UI endpoint for the deep agent and the micro-app gateway."""

import logging
from contextlib import AsyncExitStack, asynccontextmanager

from ag_ui_langgraph import add_langgraph_fastapi_endpoint
from fastapi import FastAPI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from ..agent import build_agent
from ..settings import AGENT_NAME, get_settings
from .agui import ArgsAgent
from .files import router as files_router
from .history import router as history_router
from .proxy import router
from .sessions import router as sessions_router


def create_app(graph=None) -> FastAPI:
    """Builds the service. With no graph it connects to the real MCP server and model."""
    logging.basicConfig(level=logging.INFO)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with AsyncExitStack() as stack:
            if graph is None:
                # Threads live on disk, so a restart keeps each conversation's state (sandbox, apps).
                db = get_settings().checkpoint_db
                db.parent.mkdir(parents=True, exist_ok=True)
                saver = await stack.enter_async_context(AsyncSqliteSaver.from_conn_string(str(db)))
                # Tool discovery is async, so the agent is built once the event loop is running.
                built = await build_agent(checkpointer=saver)
            else:
                built = graph
            app.state.graph = built
            add_langgraph_fastapi_endpoint(
                app=app,
                agent=ArgsAgent(
                    name=AGENT_NAME,
                    description="Builds and hosts micro-apps in isolated sandboxes",
                    graph=built,
                    # Backstop only: the real bounds are the model-call limits in agent/limits.py.
                    config={"recursion_limit": 400},
                ),
                path="/ag-ui",
            )
            yield

    app = FastAPI(title="Sandbox micro-apps agent", lifespan=lifespan)
    app.include_router(router)
    app.include_router(files_router)
    app.include_router(sessions_router)
    app.include_router(history_router)

    @app.get("/health")
    async def health() -> dict:
        cfg = get_settings()
        return {"status": "healthy", "mcp_url": cfg.mcp_url, "model": cfg.llm_model}

    return app


def serve() -> None:
    """Console entry point: `sandbox-agent` (host/port via HOST/PORT, default 0.0.0.0:8000)."""
    import os

    import uvicorn

    uvicorn.run(
        create_app, factory=True,
        host=os.environ.get("HOST", "0.0.0.0"), port=int(os.environ.get("PORT", "8000")),
    )
