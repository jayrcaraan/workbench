"""
Guard for the agent framework's own file tools (read_file, write_file, edit_file, ls, glob, grep).

They work on the agent's private scratch space and on /skills, never on a sandbox. The model kept pointing them
at sandbox paths, got "file not found" / "no matches" and burned its whole call budget (one run hit 40/40 on a
5-line edit). Calls outside /skills are answered immediately with what to use instead.
"""

from langchain.agents.middleware import wrap_tool_call
from langchain_core.messages import ToolMessage

BUILTIN = {"read_file", "write_file", "edit_file", "ls", "glob", "grep"}

REDIRECT = (
    "Error: `{tool}` only works on the agent's private scratch space and /skills, not on the sandbox, so "
    "{path!r} is not there. For sandbox files use: sbx_read_file / sbx_write_file / sbx_list_files / "
    "sbx_delete_file. To search a sandbox use sbx_run_command (`grep -rn PATTERN dir`). To change a few lines "
    "use sbx_run_command with `sed -i` or a short python snippet, or sbx_write_file the whole file. For an app "
    "from a reference template, do not edit its code: write its fields.json instead."
)


def outside_skills(tool: str, args: dict) -> str | None:
    """The offending path when a built-in file tool targets something other than /skills, else None."""
    if tool not in BUILTIN:
        return None
    path = str(args.get("file_path") or args.get("path") or "")
    return None if path.startswith("/skills") else (path or "(no path)")


@wrap_tool_call
async def sandbox_files_use_sbx_tools(request, handler):
    call = request.tool_call
    bad = outside_skills(call["name"], call.get("args") or {})
    if bad is None:
        return await handler(request)
    return ToolMessage(content=REDIRECT.format(tool=call["name"], path=bad), tool_call_id=call["id"], status="error")


SBX_PATH_TOOLS = {"sbx_read_file", "sbx_write_file", "sbx_list_files", "sbx_delete_file"}


def with_path(tool: str, args: dict) -> dict | None:
    """`file_path` renamed to `path` for the sandbox file tools (the framework's own tools say file_path), else None."""
    if tool in SBX_PATH_TOOLS and "file_path" in args and "path" not in args:
        return {("path" if k == "file_path" else k): v for k, v in args.items()}
    return None


@wrap_tool_call
async def accept_file_path_alias(request, handler):
    """The model reaches for `file_path` after using the framework's file tools; accept it instead of failing 3 times."""
    call = request.tool_call
    fixed = with_path(call["name"], call.get("args") or {})
    if fixed is None:
        return await handler(request)
    return await handler(request.override(tool_call={**call, "args": fixed}))
