"""The deep agent: model + the sandbox MCP server's tools + publish_app + packaged skills."""

from pathlib import Path

from copilotkit import CopilotKitMiddleware
from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from langgraph.checkpoint.memory import MemorySaver

from .. import sandbox
from ..apps import AppsState, publish_app
from ..apps.data import show_dashboard
from ..llm import get_model
from ..settings import AGENT_NAME, get_settings
from .context import trim_context
from .filetools import accept_file_path_alias, sandbox_files_use_sbx_tools
from .delegation import guard_task, require_publish_after_delegation
from .limits import limits
from .prompt import DELEGATION_PROMPT, SYSTEM_PROMPT
from .retry import retry_empty_turn
from .session import announce_sandbox, one_sandbox_per_session
from .subagents import subagents
from .tools import install_reference

SKILLS_DIR = Path(__file__).parent / "skills"


READ_ONLY = {"sbx_list_apps", "sbx_list_files", "sbx_read_file", "sbx_get_sandbox_status"}


async def build_agent(model=None, checkpointer=None, delegate: bool | None = None):
    """
    delegate=True: the main agent keeps only read-only sandbox tools and `publish_app`, and hands anything
    that changes the sandbox to the app-builder / debugger subagents. delegate=False: one agent does it all.
    """
    delegate = get_settings().delegate if delegate is None else delegate
    sandbox_tools = await sandbox.tools()
    options: dict = {}
    guards: list = []
    if delegate:
        guards = [require_publish_after_delegation, guard_task]
        main_tools = [t for t in sandbox_tools if t.name in READ_ONLY] + [publish_app, show_dashboard]
        options = {"subagents": subagents(sandbox_tools, [install_reference])}
        prompt = SYSTEM_PROMPT + DELEGATION_PROMPT
    else:
        main_tools = [*sandbox_tools, publish_app, show_dashboard, install_reference]
        prompt = SYSTEM_PROMPT
    return create_deep_agent(
        model=model or get_model(),
        tools=main_tools,
        system_prompt=prompt,
        # Virtual files live in agent state; /skills/ is the skills packaged with the agent.
        backend=CompositeBackend(
            default=StateBackend(),
            routes={"/skills/": FilesystemBackend(root_dir=SKILLS_DIR, virtual_mode=True)},
        ),
        skills=["/skills/"],
        permissions=[FilesystemPermission(operations=["write"], paths=["/skills/**"], mode="deny")],
        state_schema=AppsState,
        middleware=[trim_context, retry_empty_turn, accept_file_path_alias, sandbox_files_use_sbx_tools, *guards, announce_sandbox, one_sandbox_per_session, *limits(), CopilotKitMiddleware()],
        checkpointer=checkpointer or MemorySaver(),
        name=AGENT_NAME,
        **options,
    )
