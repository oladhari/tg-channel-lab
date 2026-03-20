"use client";

import { useEffect, useState, useCallback } from "react";
import { toJST } from "../../lib/time";

function secDiff(a: string | null, b: string | null): string {
  if (!a || !b) return "—";
  const diff = (new Date(b).getTime() - new Date(a).getTime()) / 1000;
  if (diff < 0) return "—";
  return diff < 60 ? `${diff.toFixed(1)}s` : `${(diff / 60).toFixed(1)}m`;
}

function holdingSec(started: string | null, buy: string | null): string {
  if (!buy) return "—";
  const ref = buy;
  const now = Date.now();
  const diff = (now - new Date(ref).getTime()) / 1000;
  if (diff < 0) return "—";
  return diff < 60 ? `${diff.toFixed(0)}s` : `${(diff / 60).toFixed(1)}m`;
}

function statusBadge(status: string | null) {
  const s = (status || "").toUpperCase();
  const colors: Record<string, string> = {
    NONE: "#888",
    SENT: "#16a34a",
    FALLBACK_GMGN: "#d97706",
    ERROR: "#dc2626",
  };
  return (
    <span style={{
      background: colors[s] || "#ccc",
      color: "#fff",
      borderRadius: 4,
      padding: "1px 6px",
      fontSize: 11,
      fontWeight: 600,
      letterSpacing: "0.3px",
    }}>
      {s || "—"}
    </span>
  );
}

function outcomeColor(outcome: string | null) {
  if (outcome === "TP") return "#16a34a";
  if (outcome === "SL") return "#dc2626";
  if (outcome === "TIME") return "#d97706";
  return "#888";
}

export default function LiveMonitor({ initialRows }: { initialRows: any[] }) {
  const [rows, setRows] = useState<any[]>(initialRows);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());
  const [now, setNow] = useState<Date>(new Date());
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/live/queue?limit=100", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setRows(data);
      setLastRefresh(new Date());
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  // Auto-refresh every 3s
  useEffect(() => {
    const id = setInterval(refresh, 3000);
    return () => clearInterval(id);
  }, [refresh]);

  // Tick every second to update holding time column live
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const holding = rows.filter(
    (r) => r.live_buy_status === "SENT" && r.live_sell_status === "NONE"
  );
  const recent = rows.filter(
    (r) => r.live_sell_status === "SENT" || r.live_buy_status === "ERROR"
  );
  const pending = rows.filter(
    (r) => r.live_buy_status === "NONE" && r.status === "RECORDING"
  );

  return (
    <div>
      {/* Status bar */}
      <div style={{ display: "flex", gap: 20, alignItems: "center", marginBottom: 14, fontSize: 13 }}>
        <span style={{ color: "#16a34a", fontWeight: 600 }}>● LIVE</span>
        <span style={{ color: "#888" }}>
          Last refresh: {lastRefresh.toLocaleTimeString("ja-JP", { timeZone: "Asia/Tokyo" })} JST
        </span>
        {error && <span style={{ color: "crimson" }}>⚠ {error}</span>}
        <span style={{ marginLeft: "auto", color: "#888" }}>
          {holding.length} holding · {pending.length} pending buy · {recent.length} completed
        </span>
      </div>

      {/* ── Currently Holding ── */}
      <section style={{ marginBottom: 28 }}>
        <h3 style={{ margin: "0 0 8px", color: "#d97706" }}>
          Holding ({holding.length})
        </h3>
        {holding.length === 0 ? (
          <p style={{ color: "#999", fontSize: 13 }}>Nothing in wallet from this bot.</p>
        ) : (
          <table cellPadding={9} style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#fffbeb", borderBottom: "2px solid #fde68a" }}>
                <th style={{ textAlign: "left" }}>ID</th>
                <th style={{ textAlign: "left" }}>Channel</th>
                <th style={{ textAlign: "left" }}>Mint</th>
                <th style={{ textAlign: "left" }}>Signal→Buy</th>
                <th style={{ textAlign: "left" }}>Holding</th>
                <th style={{ textAlign: "left" }}>Amount</th>
                <th style={{ textAlign: "left" }}>Sell status</th>
                <th style={{ textAlign: "left" }}>Outcome</th>
                <th style={{ textAlign: "left" }}>Signal at</th>
              </tr>
            </thead>
            <tbody>
              {holding.map((r) => {
                const holdSec = r.live_buy_sent_at
                  ? ((now.getTime() - new Date(r.live_buy_sent_at).getTime()) / 1000)
                  : null;
                const holdStr = holdSec != null
                  ? holdSec < 60 ? `${holdSec.toFixed(0)}s` : `${(holdSec / 60).toFixed(1)}m`
                  : "—";
                const holdWarn = holdSec != null && holdSec > 300; // >5min = orange
                return (
                  <tr key={r.id} style={{ borderBottom: "1px solid #fef3c7" }}>
                    <td><a href={`/calls/${r.id}`} style={{ textDecoration: "underline" }}>{r.id}</a></td>
                    <td><b>{r.channel_key}</b></td>
                    <td style={{ fontFamily: "monospace", fontSize: 11 }}>
                      {r.mint ? `${String(r.mint).slice(0, 12)}…` : ""}
                    </td>
                    <td>{secDiff(r.started_at, r.live_buy_sent_at)}</td>
                    <td style={{ color: holdWarn ? "#dc2626" : "#d97706", fontWeight: 600 }}>
                      {holdStr}
                    </td>
                    <td>{r.live_buy_amount_sol != null ? `${r.live_buy_amount_sol} SOL` : "—"}</td>
                    <td>{statusBadge(r.live_sell_status)}</td>
                    <td style={{ color: outcomeColor(r.outcome), fontWeight: 600 }}>
                      {r.outcome || "—"}
                    </td>
                    <td style={{ fontSize: 11, color: "#666" }}>{toJST(r.started_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      {/* ── Pending Buy ── */}
      <section style={{ marginBottom: 28 }}>
        <h3 style={{ margin: "0 0 8px", color: "#2563eb" }}>
          Pending Buy ({pending.length})
        </h3>
        {pending.length === 0 ? (
          <p style={{ color: "#999", fontSize: 13 }}>No signals waiting for buy.</p>
        ) : (
          <table cellPadding={9} style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#eff6ff", borderBottom: "2px solid #bfdbfe" }}>
                <th style={{ textAlign: "left" }}>ID</th>
                <th style={{ textAlign: "left" }}>Channel</th>
                <th style={{ textAlign: "left" }}>Mint</th>
                <th style={{ textAlign: "left" }}>Waiting</th>
                <th style={{ textAlign: "left" }}>Signal at</th>
              </tr>
            </thead>
            <tbody>
              {pending.map((r) => {
                const waitSec = r.started_at
                  ? ((now.getTime() - new Date(r.started_at).getTime()) / 1000)
                  : null;
                const waitStr = waitSec != null
                  ? waitSec < 60 ? `${waitSec.toFixed(0)}s` : `${(waitSec / 60).toFixed(1)}m`
                  : "—";
                const waitWarn = waitSec != null && waitSec > 10;
                return (
                  <tr key={r.id} style={{ borderBottom: "1px solid #dbeafe" }}>
                    <td><a href={`/calls/${r.id}`} style={{ textDecoration: "underline" }}>{r.id}</a></td>
                    <td><b>{r.channel_key}</b></td>
                    <td style={{ fontFamily: "monospace", fontSize: 11 }}>
                      {r.mint ? `${String(r.mint).slice(0, 12)}…` : ""}
                    </td>
                    <td style={{ color: waitWarn ? "#dc2626" : "#2563eb", fontWeight: 600 }}>
                      {waitStr}
                    </td>
                    <td style={{ fontSize: 11, color: "#666" }}>{toJST(r.started_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      {/* ── Completed / Sold ── */}
      <section>
        <h3 style={{ margin: "0 0 8px", color: "#444" }}>
          Completed ({recent.length})
        </h3>
        {recent.length === 0 ? (
          <p style={{ color: "#999", fontSize: 13 }}>No completed trades yet.</p>
        ) : (
          <table cellPadding={9} style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#f8f8f8", borderBottom: "2px solid #e5e7eb" }}>
                <th style={{ textAlign: "left" }}>ID</th>
                <th style={{ textAlign: "left" }}>Channel</th>
                <th style={{ textAlign: "left" }}>Mint</th>
                <th style={{ textAlign: "left" }}>Signal→Buy</th>
                <th style={{ textAlign: "left" }}>Held</th>
                <th style={{ textAlign: "left" }}>Outcome</th>
                <th style={{ textAlign: "left" }}>PnL</th>
                <th style={{ textAlign: "left" }}>Buy status</th>
                <th style={{ textAlign: "left" }}>Sell status</th>
                <th style={{ textAlign: "left" }}>Error</th>
                <th style={{ textAlign: "left" }}>Signal at</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((r) => (
                <tr key={r.id} style={{ borderBottom: "1px solid #f0f0f0" }}>
                  <td><a href={`/calls/${r.id}`} style={{ textDecoration: "underline" }}>{r.id}</a></td>
                  <td><b>{r.channel_key}</b></td>
                  <td style={{ fontFamily: "monospace", fontSize: 11 }}>
                    {r.mint ? `${String(r.mint).slice(0, 12)}…` : ""}
                  </td>
                  <td>{secDiff(r.started_at, r.live_buy_sent_at)}</td>
                  <td>{secDiff(r.live_buy_sent_at, r.live_sell_sent_at)}</td>
                  <td style={{ color: outcomeColor(r.outcome), fontWeight: 600 }}>
                    {r.outcome || "—"}
                  </td>
                  <td style={{ color: (r.pnl_pct ?? 0) >= 0 ? "#16a34a" : "#dc2626", fontWeight: 600 }}>
                    {r.pnl_pct != null ? `${Number(r.pnl_pct).toFixed(1)}%` : "—"}
                  </td>
                  <td>{statusBadge(r.live_buy_status)}</td>
                  <td>{statusBadge(r.live_sell_status)}</td>
                  <td style={{ color: "crimson", fontSize: 11, maxWidth: 160 }}>
                    {r.live_buy_error || r.live_sell_error
                      ? String(r.live_buy_error || r.live_sell_error).slice(0, 80)
                      : ""}
                  </td>
                  <td style={{ fontSize: 11, color: "#666" }}>{toJST(r.started_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
