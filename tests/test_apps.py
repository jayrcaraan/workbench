import json
from unittest.mock import AsyncMock

import httpx
import pytest
from langchain_core.messages import ToolMessage

from sandbox_agent import sandbox
from sandbox_agent.apps import publish as apps_mod
from sandbox_agent.apps.publish import merge_apps, probe, publish_app
from sandbox_agent.apps.spec import IframeSpec, TableSpec

TABLE = TableSpec.model_validate({
    "kind": "table", "title": "T", "key": "id", "list": {"path": "/customers"},
    "columns": [{"key": "id"}],
})


def fake_access(apps=None, missing=False):
    apps = apps if apps is not None else [
        {"name": "crm", "port": 8000, "url": "http://crm.sbx-1.sandbox.localhost"}]

    async def access(sandbox_id, fresh=False):
        return None if missing else {"token": "tok", "apps": apps}

    return access


class Runtime:
    tool_call_id = "call-1"
    state = {"messages": []}


async def publish(ui, monkeypatch, *, probe_result=None, **kw):
    monkeypatch.setattr(sandbox, "access", fake_access(**kw.pop("access", {})))
    monkeypatch.setattr(apps_mod, "probe", AsyncMock(return_value=probe_result))
    args = dict(sandbox_id="sbx-1", name="crm", title="CRM", ui=ui, runtime=Runtime())
    args.update(kw)
    return await publish_app.coroutine(**args)


def test_merge_apps_upserts_by_id():
    a = [{"app_id": "s/a", "title": "1"}, {"app_id": "s/b", "title": "b"}]
    merged = merge_apps(a, [{"app_id": "s/a", "title": "2"}, {"app_id": "s/c", "title": "c"}])
    assert [m["title"] for m in merged] == ["2", "b", "c"]
    assert merge_apps(None, None) == []


@pytest.mark.asyncio
async def test_publish_success_updates_state_without_secrets(monkeypatch):
    cmd = await publish(TABLE, monkeypatch)
    apps_mod.probe.assert_awaited_once()
    assert apps_mod.probe.await_args.args[0] == "http://crm.sbx-1.sandbox.localhost/customers"
    app = cmd.update["apps"][0]
    assert app["app_id"] == "sbx-1/crm" and app["ui"]["kind"] == "table"
    assert "tok" not in json.dumps(app)
    msg = cmd.update["messages"][0]
    assert isinstance(msg, ToolMessage) and msg.tool_call_id == "call-1" and "Published" in msg.content


@pytest.mark.asyncio
async def test_publish_refuses_unexposed_app_and_missing_sandbox(monkeypatch):
    cmd = await publish(TABLE, monkeypatch, name="nope")
    assert "apps" not in cmd.update and "sbx_expose_port" in cmd.update["messages"][0].content
    cmd = await publish(TABLE, monkeypatch, access={"missing": True})
    assert "does not exist" in cmd.update["messages"][0].content


@pytest.mark.asyncio
async def test_publish_refuses_when_app_does_not_answer(monkeypatch):
    cmd = await publish(TABLE, monkeypatch, probe_result="http://x did not answer")
    assert "apps" not in cmd.update
    assert "not published" in cmd.update["messages"][0].content


@pytest.mark.asyncio
async def test_iframe_gets_direct_url_with_token(monkeypatch):
    cmd = await publish(IframeSpec(kind="iframe", title="S", path="/dash"), monkeypatch)
    assert cmd.update["apps"][0]["ui"]["url"] == "http://crm.sbx-1.sandbox.localhost/dash?token=tok"


def mock_http(monkeypatch, handler):
    monkeypatch.setattr(sandbox, "http", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(sandbox, "RETRY_DELAY_S", 0)
    monkeypatch.setattr(apps_mod, "PROBE_DELAY_S", 0)


@pytest.mark.asyncio
async def test_probe_reasons(monkeypatch):
    mock_http(monkeypatch, lambda r: httpx.Response(200, text="ok"))
    assert await probe("http://a/x", "t") is None

    mock_http(monkeypatch, lambda r: httpx.Response(404, json={}, headers={"server": "uvicorn"}))
    assert "does not exist" in await probe("http://a/x", "t")

    def boom(r):
        raise httpx.ConnectError("refused")

    mock_http(monkeypatch, boom)
    msg = await probe("http://a/x", "t")
    assert "did not answer" in msg and "sbx_read_file" in msg


@pytest.mark.asyncio
async def test_ui_may_be_a_json_string_or_a_plain_dict(monkeypatch):
    import json as _json

    as_dict = TABLE.model_dump(exclude_none=True)
    for ui in (as_dict, _json.dumps(as_dict)):
        cmd = await publish(ui, monkeypatch)
        assert cmd.update["apps"][0]["ui"]["kind"] == "table"


@pytest.mark.asyncio
async def test_invalid_ui_is_reported_with_the_fields_to_fix(monkeypatch):
    cmd = await publish({"kind": "table", "title": "T", "key": "id"}, monkeypatch)   # no list, no columns
    text = cmd.update["messages"][0].content
    assert "apps" not in cmd.update and "invalid ui spec" in text and "list" in text and "columns" in text
    cmd = await publish("not json", monkeypatch)
    assert "JSON object" in cmd.update["messages"][0].content


def test_template_apps_publish_with_their_own_fields_and_the_real_row_key():
    from sandbox_agent.apps.publish import adopt_declared_fields, columns_from_fields

    declared = {"fields": [
        {"key": "control_id", "label": "Control ID", "type": "text"},
        {"key": "due", "label": "Due", "type": "date"},
        {"key": "status", "label": "Status", "type": "select", "options": ["Open", "Done"]},
    ]}
    model_spec = {"kind": "sheet", "title": "T", "key": "control_id",   # what the model got wrong
                  "update": {"method": "PUT", "path": "/items/{control_id}"}, "columns": []}
    out = adopt_declared_fields(model_spec, declared)
    assert out["key"] == "id" and out["update"]["path"] == "/items/{id}" and out["rows_path"] == "items"
    cols = {c["key"]: c for c in out["columns"]}
    assert cols["id"]["editable"] is False and cols["control_id"]["editable"] is True
    assert cols["due"]["type"] == "date" and cols["status"]["options"] == ["Open", "Done"]
    assert [c["key"] for c in columns_from_fields(declared)][0] == "id"
    # Not a template app, or not a grid: left exactly as the model wrote it.
    assert adopt_declared_fields(model_spec, None) is model_spec
    assert adopt_declared_fields({"kind": "iframe", "title": "x"}, declared) == {"kind": "iframe", "title": "x"}


@pytest.mark.asyncio
async def test_publish_of_a_template_app_needs_only_the_kind_and_uses_its_declared_fields(monkeypatch):
    declared = {"fields": [{"key": "control_id", "label": "Control ID", "type": "text"},
                           {"key": "status", "label": "Status", "type": "select", "options": ["Open", "Done"]}]}
    monkeypatch.setattr(apps_mod, "declared_fields", AsyncMock(return_value=declared))
    cmd = await publish({"kind": "sheet", "title": "Tracker"}, monkeypatch)
    ui = cmd.update["apps"][0]["ui"]
    assert ui["key"] == "id" and ui["update"]["path"] == "/items/{id}"
    cols = {c["key"]: c for c in ui["columns"]}
    assert cols["control_id"]["editable"] is True and cols["status"]["type"] == "select"
    assert apps_mod.probe.await_args.args[0].endswith("/items")
