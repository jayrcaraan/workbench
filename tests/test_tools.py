from types import SimpleNamespace

from sandbox_agent import sandbox
from sandbox_agent.agent.tools import REFERENCES, install_reference


def RT(state=None):
    return SimpleNamespace(state=state or {})


async def test_install_reference_copies_the_file_verbatim(monkeypatch):
    seen = {}

    async def call(tool, **args):
        seen.update(tool=tool, **args)
        return {"path": "/home/sandbox/" + args["path"], "bytes": len(args["content"])}

    monkeypatch.setattr(sandbox, "call", call)
    out = await install_reference.coroutine(sandbox_id="sbx-1a2b3c4d", reference="sheet-collector.py", dest_path="workbench/collector.py", runtime=RT())
    assert seen["tool"] == "write_file" and seen["content"] == (REFERENCES / "sheet-collector.py").read_text()
    assert out.startswith("Installed")


async def test_unknown_reference_lists_available(monkeypatch):
    out = await install_reference.coroutine(sandbox_id="sbx-1a2b3c4d", reference="../etc/passwd", dest_path="x", runtime=RT())
    assert out.startswith("Error") and "sheet-collector.py" in out


async def test_install_reference_finds_files_from_every_skill(monkeypatch):
    seen = {}

    async def call(tool, **args):
        seen.update(args)
        return {"path": args["path"], "bytes": len(args["content"])}

    monkeypatch.setattr(sandbox, "call", call)
    out = await install_reference.coroutine(sandbox_id="sbx-1a2b3c4d", reference="smoke.py", dest_path="tools/smoke.py", runtime=RT())
    assert out.startswith("Installed") and "urllib" in seen["content"]


async def test_empty_sandbox_id_falls_back_to_the_session_sandbox_or_errors_clearly(monkeypatch):
    seen = {}

    async def call(tool, **args):
        seen.update(args)
        return {"path": args["path"], "bytes": 1}

    monkeypatch.setattr(sandbox, "call", call)
    ok = await install_reference.coroutine(sandbox_id="", reference="smoke.py", dest_path="t/s.py",
                                           runtime=RT({"sandbox_id": "sbx-0a1b2c3d"}))
    assert ok.startswith("Installed") and seen["sandbox_id"] == "sbx-0a1b2c3d"
    seen.clear()
    err = await install_reference.coroutine(sandbox_id="", reference="smoke.py", dest_path="t/s.py", runtime=RT())
    assert err.startswith("Error: no sandbox") and not seen
