import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sandbox_agent import sandbox
from sandbox_agent.api import proxy


def make_client(monkeypatch, handler, *, token="tok", forgotten=None):
    apps = [{"name": "crm", "port": 8000, "url": "http://crm.sbx-1.sandbox.localhost"}]

    async def access(sandbox_id, fresh=False):
        return {"token": token, "apps": apps} if sandbox_id == "sbx-1" else None

    monkeypatch.setattr(sandbox, "access", access)
    monkeypatch.setattr(sandbox, "forget", (forgotten if forgotten is not None else []).append)
    monkeypatch.setattr(sandbox, "http", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(sandbox, "RETRY_DELAY_S", 0)
    app = FastAPI()
    app.include_router(proxy.router)
    return TestClient(app)


def test_forwards_with_server_side_token_and_never_leaks_it(monkeypatch):
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        seen["auth"] = req.headers.get("authorization")
        seen["cookie"] = req.headers.get("cookie")
        return httpx.Response(200, json=[{"id": 1}], headers={"set-cookie": "x=1"})

    c = make_client(monkeypatch, handler)
    r = c.get("/apps/sbx-1/crm/records?limit=5", headers={"cookie": "browser=secret", "authorization": "Bearer evil"})
    assert r.status_code == 200 and r.json() == [{"id": 1}]
    assert seen["url"] == "http://crm.sbx-1.sandbox.localhost/records?limit=5"
    assert seen["auth"] == "Bearer tok"          # replaced, not the browser's
    assert seen["cookie"] is None                # browser cookies are not forwarded
    assert "set-cookie" not in r.headers


def test_post_body_and_status_passthrough(monkeypatch):
    def handler(req: httpx.Request):
        assert req.method == "POST" and req.content == b'{"name":"Ada"}'
        return httpx.Response(422, json={"detail": "bad"})

    r = make_client(monkeypatch, handler).post("/apps/sbx-1/crm/records", content=b'{"name":"Ada"}',
                                  headers={"content-type": "application/json"})
    assert r.status_code == 422 and r.json() == {"detail": "bad"}


def test_unknown_sandbox_and_app(monkeypatch):
    def handler(req):  # must never be reached
        raise AssertionError("upstream called")

    c = make_client(monkeypatch, handler)
    assert c.get("/apps/sbx-zzz/crm/x").json()["error"] == "sandbox_not_found"
    r = c.get("/apps/sbx-1/other/x")
    assert r.status_code == 404 and r.json()["error"] == "app_not_found"


def test_retries_nginx_ingress_lag_for_get(monkeypatch):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(404, text="nginx 404", headers={"server": "nginx"})
        return httpx.Response(200, text="ok")

    r = make_client(monkeypatch, handler).get("/apps/sbx-1/crm/")
    assert r.status_code == 200 and calls["n"] == 3


def test_app_own_404_is_not_retried(monkeypatch):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(404, json={"detail": "Not Found"}, headers={"server": "uvicorn"})

    r = make_client(monkeypatch, handler).get("/apps/sbx-1/crm/missing")
    assert r.status_code == 404 and calls["n"] == 1


def test_unreachable_and_timeout_are_mapped(monkeypatch):

    def refuse(req):
        raise httpx.ConnectError("refused")

    def slow(req):
        raise httpx.ReadTimeout("slow")

    assert make_client(monkeypatch, refuse).get("/apps/sbx-1/crm/x").status_code == 502
    assert make_client(monkeypatch, slow).get("/apps/sbx-1/crm/x").status_code == 504


def test_401_drops_cached_access(monkeypatch):
    forgotten = []
    c = make_client(monkeypatch, lambda req: httpx.Response(401, text="no"), forgotten=forgotten)
    r = c.get("/apps/sbx-1/crm/x")
    assert r.status_code == 401 and forgotten == ["sbx-1"]
