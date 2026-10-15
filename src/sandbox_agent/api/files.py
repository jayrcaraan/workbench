"""
File browser API: list and preview the user's home directory through a running sandbox.

The home volume is shared by all of the user's sandboxes, so any live sandbox shows the same files.
Read-only: it uses the MCP server's list_files / read_file tools, which confine paths to the home.
"""

import base64
import mimetypes
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from .. import sandbox

router = APIRouter(prefix="/files")

_SANDBOX = re.compile(r"^sbx-[0-9a-f]{6,}$")
PREVIEW_BYTES = 256 * 1024
TEXT_SUFFIXES = {".txt", ".md", ".py", ".js", ".ts", ".tsx", ".json", ".jsonl", ".csv", ".tsv", ".yaml", ".yml",
                 ".toml", ".ini", ".cfg", ".log", ".sh", ".sql", ".html", ".css", ".xml", ".env", ".ndjson"}


def _check(sandbox_id: str) -> None:
    if not _SANDBOX.match(sandbox_id):
        raise HTTPException(400, "invalid sandbox id")


async def _call(tool: str, **args: Any) -> dict[str, Any]:
    try:
        return await sandbox.call(tool, **args)
    except RuntimeError as e:
        text = str(e)
        status = 404 if "does not exist" in text or "no such" in text.lower() else 502
        raise HTTPException(status, text.replace("Error executing tool ", "")[:300]) from None


@router.get("")
async def list_dir(sandbox_id: str = Query(...), path: str = Query("")) -> dict[str, Any]:
    _check(sandbox_id)
    res = await _call("list_files", sandbox_id=sandbox_id, **({"path": path} if path else {}))
    entries = sorted(res.get("entries", []), key=lambda e: (e["type"] != "dir", e["name"].lower()))
    return {"sandbox_id": sandbox_id, "path": res.get("path", path), "entries": entries}


@router.get("/read")
async def read_file(sandbox_id: str = Query(...), path: str = Query(...), max_bytes: int = Query(PREVIEW_BYTES, le=2_000_000)) -> dict[str, Any]:
    _check(sandbox_id)
    res = await _call("read_file", sandbox_id=sandbox_id, path=path, encoding="base64", max_bytes=max_bytes)
    raw = base64.b64decode(res.get("content", "") or "")
    suffix = "." + path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    text: str | None = None
    if suffix in TEXT_SUFFIXES or mime.startswith("text/") or mime == "application/json":
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = None
    out: dict[str, Any] = {
        "path": res.get("path", path), "size": res.get("size", len(raw)), "truncated": bool(res.get("truncated")),
        "mime": mime, "suffix": suffix, "text": text,
    }
    if text is None and mime.startswith("image/") and len(raw) <= 1_500_000:
        out["image_b64"] = base64.b64encode(raw).decode("ascii")
    return out
