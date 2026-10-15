"""Agent tool for deploying the skill's reference files into a sandbox without the model retyping them."""

import re
from pathlib import Path

from langchain.tools import ToolRuntime, tool

from .. import sandbox

SKILLS = Path(__file__).parent / "skills"
REFERENCES = SKILLS / "micro-apps" / "references"  # the micro-apps skill's reference files


def _references() -> dict[str, Path]:
    """Every file in any skill's references/ directory, by file name."""
    return {p.name: p for d in sorted(SKILLS.glob("*/references")) for p in sorted(d.iterdir()) if p.is_file()}


@tool
async def install_reference(sandbox_id: str, reference: str, dest_path: str, runtime: ToolRuntime) -> str:
    """
    Copy a reference file from a skill's references/ directory into the sandbox, byte for byte.
    Use this to deploy a reference app (e.g. `sheet-collector.py`, `data-service.py`, `app-template.py`, `smoke.py`) instead of retyping it.

    Args:
        sandbox_id: Target sandbox, e.g. 'sbx-1a2b3c4d'. Leave empty to use this session's sandbox.
        reference: File name under any skill's references/ directory.
        dest_path: Destination inside the sandbox home, e.g. 'workbench/collector.py'.
    """
    sandbox_id = (sandbox_id or "").strip() or str(runtime.state.get("sandbox_id") or "")
    if not re.fullmatch(r"sbx-[0-9a-f]{6,}", sandbox_id):
        return (
            "Error: no sandbox to install into. Create one with sbx_create_sandbox first (or pass the "
            f"sandbox_id it returned); got {sandbox_id!r}."
        )
    found = _references()
    if reference not in found:
        return f"Error: unknown reference {reference!r}. Available: {', '.join(sorted(found))}"
    res = await sandbox.call("write_file", sandbox_id=sandbox_id, path=dest_path, content=found[reference].read_text())
    return f"Installed {reference} to {res.get('path', dest_path)} ({res.get('bytes', '?')} bytes)."
