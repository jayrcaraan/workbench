// UI specs published by the agent (mirrors src/sandbox_agent/apps/spec.py).

export type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

/** Route relative to the app root. `{<key>}` in the path is replaced by the row's key value. */
export interface Route {
  method?: Method;
  path: string;
}

/** A table column, a form field or a metric, depending on where it is used. */
export interface Item {
  key: string;
  label?: string;
  type?: "text" | "number" | "currency" | "boolean" | "checkbox" | "date" | "textarea" | "select";
  options?: string[]; // select
  editable?: boolean; // table columns
  required?: boolean; // form fields
  format?: "number" | "currency" | "percent" | "text"; // metrics
}

export interface TableSpec {
  kind: "table";
  title: string;
  list: Route;
  create?: Route;
  update?: Route;
  delete?: Route;
  rows_path?: string;
  key: string;
  columns: Item[];
}
/** Spreadsheet-style typed grid; same contract as `table`. */
export interface SheetSpec {
  kind: "sheet";
  title: string;
  list: Route;
  create?: Route;
  update?: Route;
  delete?: Route;
  rows_path?: string;
  key: string;
  columns: Item[];
}
export type PanelType = "metric" | "table" | "bar" | "column" | "line" | "donut" | "progress" | "details" | "note";
export interface Panel {
  title: string;
  description?: string;
  type?: PanelType;
  path?: string; // data file relative to the sandbox home
  sql?: string; // one read-only SELECT; csv/parquet/json files are the table `data`
  x?: string;
  y?: string;
  target?: string; // progress: goal column or number
  format?: "number" | "currency" | "percent" | "text";
  text?: string; // note
  tone?: "info" | "success" | "warning";
  wide?: boolean;
  /** Rows of the query, embedded by the agent service. */
  result?: { columns: string[]; rows: unknown[][]; truncated?: boolean; error?: string };
}
/** Panels rendered from SQL results the agent service ran in the sandbox; no app involved. */
export interface DashboardSpec {
  kind: "dashboard";
  title: string;
  panels: Panel[];
}
export interface FormSpec {
  kind: "form";
  title: string;
  submit: Route;
  fields: Item[];
}
export interface MetricsSpec {
  kind: "metrics";
  title: string;
  source: Route;
  items: Item[];
  refresh_s?: number;
}
export interface IframeSpec {
  kind: "iframe";
  title: string;
  path?: string;
  url?: string;
}

export type UiSpec = TableSpec | SheetSpec | DashboardSpec | FormSpec | MetricsSpec | IframeSpec;

/** One published micro-app, as streamed in agent state (`state.apps`). No secrets. */
export interface PublishedApp {
  app_id: string; // "<sandbox_id>/<name>"
  name: string;
  title: string;
  ui: UiSpec;
}

export interface AgentState {
  apps?: PublishedApp[];
}
