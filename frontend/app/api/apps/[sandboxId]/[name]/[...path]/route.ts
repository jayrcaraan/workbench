// Same-origin gateway to micro-apps. The agent service owns the sandbox token;
// this route only forwards and streams. The LLM is never in this path.
import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const AGENT_BASE = (process.env.AGENT_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

const FORWARD = ["content-type", "accept", "accept-language", "if-none-match", "range"];

async function forward(
  req: NextRequest,
  { params }: { params: { sandboxId: string; name: string; path: string[] } }
) {
  const { sandboxId, name, path } = params;
  const target = `${AGENT_BASE}/apps/${encodeURIComponent(sandboxId)}/${encodeURIComponent(name)}/${path
    .map(encodeURIComponent)
    .join("/")}${req.nextUrl.search}`;

  const headers = new Headers();
  FORWARD.forEach((h) => {
    const v = req.headers.get(h);
    if (v) headers.set(h, v);
  });

  const hasBody = !["GET", "HEAD"].includes(req.method);
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers,
      body: hasBody ? await req.arrayBuffer() : undefined,
      cache: "no-store",
    });
  } catch (e: any) {
    return Response.json(
      { error: "gateway_unreachable", message: `Agent service unreachable: ${e?.message ?? e}` },
      { status: 502 }
    );
  }

  const out = new Headers();
  ["content-type", "content-length", "content-disposition", "etag", "cache-control"].forEach((h) => {
    const v = upstream.headers.get(h);
    if (v) out.set(h, v);
  });
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const PATCH = forward;
export const DELETE = forward;
