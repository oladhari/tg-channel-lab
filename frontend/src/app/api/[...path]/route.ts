// frontend/src/app/api/[...path]/route.ts
import { NextRequest, NextResponse } from "next/server";

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

  const headers = new Headers();

  // forward content-type if present
  const ct = req.headers.get("content-type");
  if (ct) headers.set("content-type", ct);

  // forward auth if present (future-proof)
  const auth = req.headers.get("authorization");
  if (auth) headers.set("authorization", auth);

  // forward cookies if present (future-proof)
  const cookie = req.headers.get("cookie");
  if (cookie) headers.set("cookie", cookie);

  const init: RequestInit = {
    method: req.method,
    headers,
    cache: "no-store",
  };

  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.text();
  }

  const res = await fetch(url, init);
  const body = await res.text();

  return new NextResponse(body, {
    status: res.status,
    headers: {
      "content-type": res.headers.get("content-type") || "application/json",
    },
  });
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
