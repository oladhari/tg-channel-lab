// frontend/src/lib/api.ts

function backendBase(): string {
  // SSR (inside docker) -> talk directly to backend service
  const b = process.env.BACKEND_URL || "http://api:8000";
  return b.replace(/\/$/, "");
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const p = path.startsWith("/") ? path : `/${path}`;

  // Browser -> go through Next proxy (/api)
  // SSR -> direct to backend
  const url = typeof window !== "undefined" ? `/api${p}` : `${backendBase()}${p}`;

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
      const msg = (j as any)?.detail || (j as any)?.message || JSON.stringify(j);
      throw new Error(`HTTP ${res.status} ${res.statusText} — ${msg}`);
    }
    const text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} ${res.statusText} — ${text.slice(0, 250)}`);
  }

  // Some endpoints might return empty body; handle safely
  const text = await res.text();
  if (!text) return undefined as unknown as T;
  return JSON.parse(text) as T;
}

export type Channel = {
  id: number;
  key: string;
  telegram_username: string;
  enabled: boolean;
  live_enabled: boolean;
  live_buy_amount_sol: number | null;
  live_tp_pct: number | null;
  live_sl_pct: number | null;
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

export function createChannel(body: {
  key: string;
  telegram_username: string;
  enabled: boolean;
  live_enabled: boolean;

  // ✅ NEW
  live_buy_amount_sol?: number | null;
}) {
  return http<Channel>("/channels", { method: "POST", body: JSON.stringify(body) });
}

export function toggleChannelEnabled(id: number) {
  return http<Channel>(`/channels/${id}/toggle`, { method: "POST" });
}

// ✅ This is the ONLY correct endpoint for Live toggling
export function toggleChannelLive(id: number) {
  return http<Channel>(`/channels/${id}/toggle-live`, { method: "POST" });
}

// ✅ NEW: PATCH channel (generic updater)
export function updateChannel(
  id: number,
  body: Partial<{
    enabled: boolean;
    live_enabled: boolean;
    telegram_username: string;
    live_buy_amount_sol: number | null;
    live_tp_pct: number | null;
    live_sl_pct: number | null;
  }>
) {
  return http<Channel>(`/channels/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}

// ✅ NEW: convenience setter
export function setChannelLiveBuyAmount(id: number, amountSol: number | null) {
  return updateChannel(id, { live_buy_amount_sol: amountSol });
}

// --- Calls / stats ---
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

export type PricePoint = { t_sec: number; price_usd: number };

export function getPaperStats(params?: {
  strategy_key?: string;
  start_balance_sol?: number;
  entry_sol?: number;
  channel_key?: string;
}) {
  const strategy_key = params?.strategy_key ?? "tp35_sl20";
  const start_balance_sol = params?.start_balance_sol ?? 1.0;

  const qs = new URLSearchParams({
    strategy_key,
    start_balance_sol: String(start_balance_sol),
  });

  if (params?.entry_sol != null) qs.set("entry_sol", String(params.entry_sol));
  if (params?.channel_key) qs.set("channel_key", params.channel_key);

  return http<PaperStat[]>(`/stats/paper?${qs.toString()}`);
}

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

// --- Live (read-only endpoints) ---
export type LiveConfig = {
  gmgn_target_set: boolean;
  gmgn_target: string | null;
  gmgn_sell_percent: string;
  live_strategy_key: string;
};

export function getLiveConfig() {
  return http<LiveConfig>(`/live/config`);
}

export type WalletInfo = {
  pubkey: string | null;
  sol_balance: number | null;
  total_buys: number;
  total_sells: number;
  holding: number;
  live_channels: Array<{
    id: number;
    key: string;
    telegram_username: string;
    live_buy_amount_sol: number | null;
  }>;
};

export function getWallet() {
  return http<WalletInfo>(`/live/wallet`);
}

export function getLiveQueue(params?: { limit?: number }) {
  const qs = new URLSearchParams();
  qs.set("limit", String(params?.limit ?? 200));
  return http<any[]>(`/live/queue?${qs.toString()}`);
}

export function markCallSold(id: number) {
  return http<{ ok: boolean; call_id: number }>(`/live/calls/${id}/mark-sold`, { method: "POST" });
}

export type OnChainTrade = {
  signature: string;
  timestamp: number | null;
  direction: "BUY" | "SELL" | "SWAP" | null;
  mint: string | null;
  sol_amount: number | null;
  token_amount: number | null;
  dex: string;
  description: string;
  call: {
    id: number;
    mint: string;
    symbol: string | null;
    started_at: string;
    entry_price_usd: number | null;
    live_buy_status: string;
    live_sell_status: string;
    live_sell_reason: string | null;
    live_buy_amount_sol: number | null;
    strategy_key: string | null;
    outcome: string | null;
    pnl_pct: number | null;
    exit_price_usd: number | null;
  } | null;
};

export type WalletHistory = {
  pubkey: string | null;
  trades: OnChainTrade[];
  error: string | null;
};

export function getWalletHistory(limit = 50) {
  return http<WalletHistory>(`/live/wallet-history?limit=${limit}`);
}

export type BestStat = {
  channel_id: number;
  key: string;
  telegram_username: string;
  best_tp_pct: number;
  best_sl_pct: number;
  n_trades: number;
  tp: number;
  sl: number;
  time: number;
  win_rate_tp_pct: number;
  avg_pnl_pct: number;
  start_balance_sol: number;
  end_balance_sol: number;
  computed_at: number;
};

export function getBestStats(params?: {
  start_balance_sol?: number;
  entry_sol?: number;
}) {
  const qs = new URLSearchParams();
  qs.set("start_balance_sol", String(params?.start_balance_sol ?? 1.0));
  if (params?.entry_sol != null) qs.set("entry_sol", String(params.entry_sol));
  return http<BestStat[]>(`/stats/best?${qs.toString()}`);
}

export type GridCell = {
  tp_pct: number;
  sl_pct: number;
  n_trades: number;
  tp: number;
  sl: number;
  time: number;
  win_rate_tp_pct: number;
  avg_pnl_pct: number;
  start_balance_sol: number;
  end_balance_sol: number;
};

export type GridSim = {
  channel_key: string;
  start_balance_sol: number;
  entry_sol: number;
  tp_values: number[];
  sl_values: number[];
  results: GridCell[];
};

export function getGridSim(params: {
  channel_key: string;
  tp_values?: string;
  sl_values?: string;
  start_balance_sol?: number;
  entry_sol?: number;
  accurate?: boolean;
}) {
  const qs = new URLSearchParams();
  qs.set("channel_key", params.channel_key);
  qs.set("tp_values", params.tp_values ?? "35,40,45,50,55,60,65");
  qs.set("sl_values", params.sl_values ?? "20,25,30,35,40,45,50");
  qs.set("start_balance_sol", String(params.start_balance_sol ?? 1.0));
  if (params.entry_sol != null) qs.set("entry_sol", String(params.entry_sol));

  const endpoint = params.accurate ? "/stats/accurate-grid" : "/stats/grid";
  return http<GridSim>(`${endpoint}?${qs.toString()}`);
}
