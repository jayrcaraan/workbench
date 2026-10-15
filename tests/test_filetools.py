import pytest

from sandbox_agent.agent.filetools import outside_skills, sandbox_files_use_sbx_tools, with_path


def test_builtin_tools_are_only_allowed_on_skills():
    assert outside_skills("read_file", {"file_path": "/skills/micro-apps/SKILL.md"}) is None
    assert outside_skills("grep", {"pattern": "x", "path": "/skills/micro-apps"}) is None
    assert outside_skills("edit_file", {"file_path": "/home/sandbox/app/main.py"}) == "/home/sandbox/app/main.py"
    assert outside_skills("grep", {"pattern": "x", "path": "trip_checklist"}) == "trip_checklist"
    assert outside_skills("ls", {}) == "(no path)"
    assert outside_skills("sbx_read_file", {"path": "anything"}) is None   # the real tools are untouched


class Req:
    def __init__(self, name, args):
        self.tool_call = {"name": name, "args": args, "id": "c1"}


@pytest.mark.asyncio
async def test_misdirected_call_gets_a_redirect_without_running():
    ran = []

    async def handler(req):
        ran.append(req)

    out = await sandbox_files_use_sbx_tools.awrap_tool_call(Req("edit_file", {"file_path": "/home/sandbox/x.py"}), handler)
    assert not ran and out.status == "error" and "sbx_write_file" in out.content and "fields.json" in out.content
    await sandbox_files_use_sbx_tools.awrap_tool_call(Req("read_file", {"file_path": "/skills/a.md"}), handler)
    assert len(ran) == 1


def test_file_path_is_accepted_for_sandbox_file_tools():
    assert with_path("sbx_write_file", {"file_path": "a/b.json", "content": "{}"}) == {"path": "a/b.json", "content": "{}"}
    assert with_path("sbx_write_file", {"path": "a", "file_path": "b"}) is None      # path wins, nothing to fix
    assert with_path("write_file", {"file_path": "/skills/x"}) is None               # the framework's own tool
