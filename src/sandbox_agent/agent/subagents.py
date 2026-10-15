"""
Delegation: the main agent plans and publishes; sandbox-changing work runs in short-lived subagents.

A subagent has its own context (its tool noise never reaches the main agent's history), its own budget
of model calls, and only the tools it needs. The main agent gets back a short result.
"""

from deepagents import SubAgent

from .context import trim_context
from .limits import SUBAGENT_RUN_CALLS, limits
from .retry import retry_empty_turn
from .session import one_sandbox_per_session

BUILDER_PROMPT = """You are the app-builder. You change the user's sandbox: create it (only if the task has no sandbox_id), write files, start processes, expose ports.

Read the `micro-apps` skill first and follow it exactly (verify on localhost inside the sandbox, bind 0.0.0.0, restart on the same port, never kill other apps, one sandbox).

You have a small budget of steps. If you cannot get it working, stop and report what you saw (exact error, log lines); do not keep retrying.

Finish with a short report, nothing else:
- sandbox_id
- app name, port, and the routes that work (method + path, with a sample response)
- if you could not finish: what failed and the evidence"""

DEBUGGER_PROMPT = """You are the debugger. An app in the user's sandbox is not answering or misbehaving. Find out why and fix it.

Read the `micro-apps` skill's troubleshooting section first. Work from evidence: `curl localhost:<port>/...` inside the sandbox, the app's log file, `sbx_list_apps`. Change one thing at a time. Never kill other apps' processes.

You have a small budget of steps. Finish with a short report: what was wrong, what you changed, and whether it now answers (with the curl output)."""


def subagents(sandbox_tools: list, extra_tools: list) -> list[SubAgent]:
    tools = [*sandbox_tools, *extra_tools]
    stack = [trim_context, retry_empty_turn, one_sandbox_per_session, *limits(SUBAGENT_RUN_CALLS, one_sandbox=False)]
    return [
        SubAgent(
            name="app-builder",
            description=(
                "Does everything that changes the sandbox: creates it if needed, writes code, starts the app, "
                "exposes it, deploys reference apps (e.g. the sheet collector). Give it the full request and the "
                "sandbox_id if one exists. Returns sandbox_id, app name, port and working routes."
            ),
            system_prompt=BUILDER_PROMPT,
            tools=tools,
            skills=["/skills/"],
            middleware=stack,
        ),
        SubAgent(
            name="debugger",
            description=(
                "Diagnoses and fixes an app that does not answer or misbehaves (crash, wrong port, import error). "
                "Give it the sandbox_id, app name, port and the symptom."
            ),
            system_prompt=DEBUGGER_PROMPT,
            tools=tools,
            skills=["/skills/"],
            middleware=stack,
        ),
    ]
