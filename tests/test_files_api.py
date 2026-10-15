import base64

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sandbox_agent import sandbox
from sandbox_agent.api import files


def client(monkeypatch, handler):
    async def call(tool, **args):
        return handler(tool, **args)

    monkeypatch.setattr(sandbox, "call", call)
    app = FastAPI()
    app.include_router(files.router)
    return TestClient(app)


def test_listing_sorts_directories_first(monkeypatch):
    def handler(tool, **a):
        assert tool == "list_files" and a["sandbox_id"] == "sbx-0a1b2c3d"
        return {"path": "/home/sandbox", "entries": [
            {"name": "b.csv", "type": "file", "size": 5, "mtime": 1},
            {"name": "Zdir", "type": "dir", "size": 0, "mtime": 1},
            {"name": "adir", "type": "dir", "size": 0, "mtime": 1}]}

    c = client(monkeypatch, handler)
    out = c.get("/files", params={"sandbox_id": "sbx-0a1b2c3d"}).json()
    assert [e["name"] for e in out["entries"]] == ["adir", "Zdir", "b.csv"]


def test_preview_returns_text_for_text_files_and_images_inline(monkeypatch):
    blobs = {"notes.md": b"# hi", "pic.png": b"\x89PNG\r\n\x1a\n", "data.duckdb": b"\x00\x01\xff"}

    def handler(tool, **a):
        raw = blobs[a["path"]]
        return {"path": "/home/sandbox/" + a["path"], "size": len(raw), "truncated": False,
                "content": base64.b64encode(raw).decode()}

    c = client(monkeypatch, handler)
    q = lambda p: c.get("/files/read", params={"sandbox_id": "sbx-0a1b2c3d", "path": p}).json()
    assert q("notes.md")["text"] == "# hi"
    assert q("pic.png")["text"] is None and q("pic.png")["image_b64"]
    binary = q("data.duckdb")
    assert binary["text"] is None and "image_b64" not in binary


def test_bad_sandbox_id_and_missing_sandbox(monkeypatch):
    def handler(tool, **a):
        raise RuntimeError("Sandbox sbx-0a1b2c3d does not exist (it was destroyed or expired).")

    c = client(monkeypatch, handler)
    assert c.get("/files", params={"sandbox_id": "../x"}).status_code == 400
    r = c.get("/files", params={"sandbox_id": "sbx-0a1b2c3d"})
    assert r.status_code == 404 and "does not exist" in r.json()["detail"]
