import { CopilotRuntime, createCopilotRuntimeHandler } from "@copilotkit/runtime/v2";
import { HttpAgent } from "@ag-ui/client";

const AGENT_BASE = (process.env.AGENT_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

const runtime = new CopilotRuntime({
  agents: {
    sandbox_agent: new HttpAgent({ url: `${AGENT_BASE}/ag-ui` }),
  },
});

const handler = createCopilotRuntimeHandler({ runtime, basePath: "/api/copilotkit" });

// Optional catch-all: the runtime serves /info, /agent/<name>/run, ... under this base path.
export const GET = handler;
export const POST = handler;
