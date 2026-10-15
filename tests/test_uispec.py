import pytest
from pydantic import TypeAdapter, ValidationError

from sandbox_agent.apps.spec import UiSpec

ui = TypeAdapter(UiSpec)

TABLE = {
    "kind": "table", "title": "Customers", "key": "id",
    "list": {"method": "GET", "path": "/customers"},
    "create": {"method": "POST", "path": "/customers"},
    "update": {"method": "PUT", "path": "/customers/{id}"},
    "columns": [{"key": "id", "type": "number", "editable": False}, {"key": "name"}],
}


def test_table_roundtrip():
    spec = ui.validate_python(TABLE)
    assert spec.kind == "table" and spec.columns[1].type == "text"


def test_discriminator_selects_kind():
    assert ui.validate_python({"kind": "iframe", "title": "x"}).path == "/"
    assert ui.validate_python(
        {"kind": "metrics", "title": "m", "source": {"path": "/stats"}, "items": [{"key": "n"}]}
    ).items[0].format == "number"


@pytest.mark.parametrize("bad", [
    {**TABLE, "kind": "chart"},
    {**TABLE, "columns": [{"field": "id", "type": "string"}]},          # wrong field names
    {**TABLE, "list": {"method": "GET", "path": "customers"}},          # not absolute
    {**TABLE, "list": {"method": "GET", "path": "/a/../b"}},            # traversal
    {**TABLE, "list": {"method": "TRACE", "path": "/a"}},
])
def test_rejects_invalid(bad):
    with pytest.raises(ValidationError):
        ui.validate_python(bad)


def test_dashboard_panels_validate_and_are_not_publishable_as_an_app():
    from sandbox_agent.apps.spec import DashboardSpec

    spec = DashboardSpec.model_validate({
        "kind": "dashboard", "title": "Sales",
        "panels": [
            {"title": "Total", "type": "metric", "path": "sales.csv", "sql": "select sum(amount) t from data", "y": "t"},
            {"title": "By region", "type": "bar", "path": "sales.csv",
             "sql": "select region, sum(amount) t from data group by 1", "x": "region", "y": "t", "wide": True},
        ],
    })
    assert spec.panels[1].type == "bar" and spec.panels[0].format == "number" and spec.panels[0].result is None
    for bad in ({"kind": "dashboard", "title": "x", "panels": []},
                {"kind": "dashboard", "title": "x", "panels": [{"title": "t", "type": "pie", "path": "a.csv", "sql": "select 1"}]}):
        with pytest.raises(ValidationError):
            DashboardSpec.model_validate(bad)
    with pytest.raises(ValidationError):   # publish_app's union does not include dashboards
        ui.validate_python(spec.model_dump())
