"""
Declarative UI specs the agent publishes for a micro-app.

The frontend renders these with a fixed set of generic components; every route
is relative to the app root and reaches the app through the gateway proxy.
Mirrored by frontend/lib/uiSpec.ts.
"""

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, model_validator


def _check_path(path: str) -> str:
    if not path.startswith("/"):
        raise ValueError("path must start with '/' (relative to the app root)")
    if ".." in path.split("/"):
        raise ValueError("path must not contain '..'")
    return path


Path = Annotated[str, AfterValidator(_check_path)]


class Route(BaseModel):
    """HTTP route on the app. For update/delete, `{<key>}` is replaced by the row's key value."""

    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    path: Path


class Item(BaseModel):
    """A table column, a form field or a metric, depending on where it is used."""

    key: str
    label: str | None = None
    type: Literal["text", "number", "currency", "boolean", "checkbox", "date", "textarea", "select"] = "text"
    options: list[str] = []  # select fields
    editable: bool = True  # table columns
    required: bool = False  # form fields
    format: Literal["number", "currency", "percent", "text"] = "number"  # metrics


class TableSpec(BaseModel):
    kind: Literal["table"]
    title: str
    list: Route
    create: Route | None = None
    update: Route | None = None
    delete: Route | None = None
    rows_path: str | None = Field(
        default=None, description="Key in the list response holding the rows, e.g. 'items'"
    )
    key: str = Field(description="Column that uniquely identifies a row, e.g. 'id'")
    columns: list[Item]


class SheetSpec(BaseModel):
    """A spreadsheet-style typed grid. Same contract as `table`; every edit goes to the app's routes."""

    kind: Literal["sheet"]
    title: str
    list: Route
    create: Route | None = None
    update: Route | None = None
    delete: Route | None = None
    rows_path: str | None = Field(
        default=None, description="Key in the list response holding the rows, e.g. 'items'"
    )
    key: str = Field(description="Field that uniquely identifies a row, e.g. 'id'")
    columns: list[Item]


class PanelResult(BaseModel):
    """Rows of a panel's query, filled in by `show_dashboard` (never by the model)."""

    columns: list[str]
    rows: list[list]
    truncated: bool = False
    error: str | None = None


PanelType = Literal["metric", "table", "bar", "column", "line", "donut", "progress", "details", "note"]


class Panel(BaseModel):
    """
    One dashboard card. Data cards run a read-only SQL query against a file in the user's home; `note` cards
    are plain text and need no query.

    metric   one number (`y`); with `x` it also draws a sparkline over the rows and shows the change
    table    rows and columns (searchable)         bar      horizontal bars: `x` label, `y` value
    column   vertical bars: `x` label, `y` value   line     area chart: `x` ordered, `y` value
    donut    share of total: `x` label, `y` value  progress `y` value against `target` (column or number)
    details  first row as a key/value list         note     `text` callout, `tone` info|success|warning
    """

    title: str
    description: str | None = Field(default=None, description="One line shown under the title")
    type: PanelType = "table"
    path: str | None = Field(default=None, description="Data file relative to home, e.g. 'sales.csv' or 'wh.duckdb'")
    sql: str | None = Field(default=None, description="One SELECT/WITH statement. csv/parquet/json files are the table `data`")
    x: str | None = Field(default=None, description="Column for the category / x axis (or the sparkline x)")
    y: str | None = Field(default=None, description="Numeric column to show or plot")
    target: str | None = Field(default=None, description="progress: column holding the goal, or a number as text")
    format: Literal["number", "currency", "percent", "text"] = "number"
    text: str | None = Field(default=None, description="note: the message (supports **bold**)")
    tone: Literal["info", "success", "warning"] = "info"
    wide: bool = Field(default=False, description="Span the full row")
    result: PanelResult | None = Field(default=None, description="Set by the tool; do not provide")

    @model_validator(mode="after")
    def _needs_query_unless_note(self) -> "Panel":
        if self.type == "note":
            if not (self.text or "").strip():
                raise ValueError("a note card needs `text`")
        elif not (self.path and self.sql):
            raise ValueError(f"a {self.type} card needs `path` and `sql`")
        return self


class DashboardSpec(BaseModel):
    """Panels rendered from SQL results. Produced by `show_dashboard`; no app is involved."""

    kind: Literal["dashboard"]
    title: str
    panels: list[Panel] = Field(min_length=1, max_length=12)


class FormSpec(BaseModel):
    kind: Literal["form"]
    title: str
    submit: Route
    fields: list[Item]


class MetricsSpec(BaseModel):
    kind: Literal["metrics"]
    title: str
    source: Route
    items: list[Item]
    refresh_s: int | None = Field(default=None, ge=1, le=3600)


class IframeSpec(BaseModel):
    kind: Literal["iframe"]
    title: str
    path: Path = "/"
    # Filled in by publish_app (direct URL incl. token); not set by the model.
    url: str | None = None


UiSpec = Annotated[TableSpec | SheetSpec | FormSpec | MetricsSpec | IframeSpec, Field(discriminator="kind")]
