// frontend/src/app/api/channels/route.ts
import { NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://backend:8000";

export async function GET() {
  const r = await fetch(`${BACKEND_URL}/channels`, {
    cache: "no-store",
  });

  const ct = r.headers.get("content-type") || "";
  const body = ct.includes("application/json") ? await r.json() : await r.text();

  return NextResponse.json(body, { status: r.status });
}

export async function POST(req: Request) {
  const payload = await req.json();

  const r = await fetch(`${BACKEND_URL}/channels`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const ct = r.headers.get("content-type") || "";
  const body = ct.includes("application/json") ? await r.json() : await r.text();

  // If backend returns text error, wrap it as JSON for frontend readability
  if (!ct.includes("application/json") && !r.ok) {
    return NextResponse.json({ detail: String(body).slice(0, 500) }, { status: r.status });
  }

  return NextResponse.json(body, { status: r.status });
}
