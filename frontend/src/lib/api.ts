// frontend/src/lib/api.ts

function baseUrl(): string {
  const publicBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
  const backendBase = process.env.BACKEND_URL || "http://api:8000";

  // Server-side (Node/SSR): MUST be absolute URL
  if (typeof window === "undefined") {
    return backendBase.replace(/\/$/, "");
  }

  // Client-side (browser): can be relative ("/api") or absolute
  return publicBase.replace(/\/$/, "");
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const p = path.startsWith("/") ? path : `/${path}`;
  const url = `${baseUrl()}${p}`;

  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      const j = await res.json().catch(() => null);
      const msg = j?.detail || j?.message || JSON.stringify(j);
      throw new Error(`HTTP ${res.status} ${res.statusText} — ${msg}`);
    }
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} ${res.statusText} — ${text}`);
  }

  return (await res.json()) as T;
}

export type Channel = {
  id: number;
  key: string;
  telegram_username: string;
  enabled: boolean;
  live_enabled: boolean;
};

export type PaperStat = {
  channel_id: number;
  key: string;
  telegram_username: string;
  strategy_key: string;
  start_balance_sol: number;
  end_balance_sol: number;
  n_trades: number;
  tp: number;
  sl: number;
  time: number;
  win_rate_tp_pct: number;
  avg_pnl_pct: number;
};

export function getChannels() {
  return http<Channel[]>("/channels");
}

export function getPaperStats(params?: { strategy_key?: string; start_balance_sol?: number }) {
  const strategy_key = params?.strategy_key ?? "tp35_sl20";
  const start_balance_sol = params?.start_balance_sol ?? 1.0;

  const qs = new URLSearchParams({
    strategy_key,
    start_balance_sol: String(start_balance_sol),
  });

  return http<PaperStat[]>(`/stats/paper?${qs.toString()}`);
}

// --- Calls Explorer types ---
export type CallRow = {
  id: number;
  channel_id: number;
  channel_key: string;
  mint: string;
  symbol?: string | null;
  status: string;
  started_at: string;
  duration_sec?: number | null;
  entry_price_usd?: number | null;
  ignore_reason?: string | null;

  // Joined strategy result (optional)
  strategy_key?: string | null;
  outcome?: string | null;
  pnl_pct?: number | null;
  exit_t_sec?: number | null;
  exit_price_usd?: number | null;
};

export type CallDetail = {
  id: number;
  channel_id: number;
  channel_key: string;
  mint: string;
  symbol?: string | null;
  status: string;
  started_at: string;
  duration_sec?: number | null;
  entry_price_usd?: number | null;
  ignore_reason?: string | null;

  strategy_results: Array<{
    strategy_key: string;
    tp_pct: number;
    sl_pct: number;
    entry_price_usd: number;
    exit_price_usd: number | null;
    exit_t_sec: number | null;
    outcome: string;
    pnl_pct: number;
  }>;
};

export type PricePoint = {
  t_sec: number;
  price_usd: number;
};

export function getCalls(params?: {
  limit?: number;
  offset?: number;
  strategy_key?: string;
  channel_key?: string;
  status?: string;
}) {
  const qs = new URLSearchParams();
  qs.set("limit", String(params?.limit ?? 200));
  qs.set("offset", String(params?.offset ?? 0));
  qs.set("strategy_key", params?.strategy_key ?? "tp35_sl20");
  if (params?.channel_key) qs.set("channel_key", params.channel_key);
  if (params?.status) qs.set("status", params.status);

  return http<CallRow[]>(`/calls?${qs.toString()}`);
}

export function getCall(id: number) {
  return http<CallDetail>(`/calls/${id}`);
}

export function getCallPrices(id: number) {
  return http<PricePoint[]>(`/calls/${id}/prices`);
}
