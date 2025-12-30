// frontend/src/app/api/channels/route.ts
import { NextResponse } from "next/server";

const BACKEND_URL = (process.env.BACKEND_URL || "http://api:8000").replace(/\/$/, "");

export async function GET() {
  const r = await fetch(`${BACKEND_URL}/channels`, { cache: "no-store" });

  const ct = r.headers.get("content-type") || "";

  if (ct.includes("application/json")) {
    const body = await r.json();
    return NextResponse.json(body, { status: r.status });
  }

  const text = await r.text();
  // wrap text so client always gets JSON from /api/*
  return NextResponse.json({ detail: text.slice(0, 1000) }, { status: r.status });
}

export async function POST(req: Request) {
  const payload = await req.json();

  const r = await fetch(`${BACKEND_URL}/channels`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const ct = r.headers.get("content-type") || "";

  if (ct.includes("application/json")) {
    const body = await r.json();
    return NextResponse.json(body, { status: r.status });
  }

  const text = await r.text();
  return NextResponse.json(
    { detail: text.slice(0, 1000) },
    { status: r.status }
  );
}
