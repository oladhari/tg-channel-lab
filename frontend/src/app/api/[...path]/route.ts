// frontend/src/app/api/[...path]/route.ts
import { NextRequest } from "next/server";

const BACKEND = (process.env.BACKEND_URL || "http://api:8000").replace(/\/$/, "");

// Next 16 typed routes: params is a Promise
type Ctx = { params: Promise<{ path: string[] }> };

function backendUrl(req: NextRequest, pathParts: string[]) {
  const path = "/" + pathParts.join("/");
  const qs = req.nextUrl.search; // includes "?" if present
  return `${BACKEND}${path}${qs}`;
}

async function proxy(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  const url = backendUrl(req, path);

  // ---- timeout (truth endpoints can be slow) ----
  const controller = new AbortController();
  const timeoutMs = 900_000; // 120s (adjust if needed)
  const t = setTimeout(() => controller.abort(), timeoutMs);

  try {
    // Forward minimal useful headers (don’t forward Host/Connection/etc)
    const headers = new Headers();

    const ct = req.headers.get("content-type");
    if (ct) headers.set("content-type", ct);

    const auth = req.headers.get("authorization");
    if (auth) headers.set("authorization", auth);

    const cookie = req.headers.get("cookie");
    if (cookie) headers.set("cookie", cookie);

    // Optional: trace/debug
    const rid = req.headers.get("x-request-id");
    if (rid) headers.set("x-request-id", rid);

    const init: RequestInit = {
      method: req.method,
      headers,
      cache: "no-store",
      signal: controller.signal,
    };

    if (req.method !== "GET" && req.method !== "HEAD") {
      // Preserve body accurately (not only text)
      init.body = await req.arrayBuffer();
    }

    const upstream = await fetch(url, init);

    // Read body as bytes (works for JSON + non-JSON)
    const buf = await upstream.arrayBuffer();

    // Copy upstream headers, remove ones that can break Next Response
    const outHeaders = new Headers(upstream.headers);
    outHeaders.delete("content-encoding");
    outHeaders.delete("transfer-encoding");
    outHeaders.delete("connection");

    // Ensure content-type is set
    if (!outHeaders.get("content-type")) {
      outHeaders.set("content-type", "application/json");
    }

    return new Response(buf, { status: upstream.status, headers: outHeaders });
  } catch (e: any) {
    const isAbort = e?.name === "AbortError";
    const msg = isAbort ? `Upstream timeout after ${timeoutMs}ms` : (e?.message || String(e));

    return new Response(JSON.stringify({ detail: msg }), {
      status: isAbort ? 504 : 502,
      headers: { "content-type": "application/json" },
    });
  } finally {
    clearTimeout(t);
  }
}

export async function GET(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx);
}
export async function POST(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx);
}
export async function PUT(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx);
}
export async function PATCH(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx);
}
export async function DELETE(req: NextRequest, ctx: Ctx) {
  return proxy(req, ctx);
}
