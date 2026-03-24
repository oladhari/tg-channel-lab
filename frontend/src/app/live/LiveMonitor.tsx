"use client";

import { useEffect, useState, useCallback } from "react";
import { toJST } from "../../lib/time";
import { gmgnSolanaTokenUrl } from "../../lib/links";
import { markCallSold, getWallet, getWalletHistory, getLiveConfig, type WalletInfo, type WalletHistory, type OnChainTrade, type LiveConfig } from "../../lib/api";

function secDiff(a: string | null, b: string | null): string {
  if (!a || !b) return "—";
  const diff = (new Date(b).getTime() - new Date(a).getTime()) / 1000;
  if (diff < 0) return "—";
  return diff < 60 ? `${diff.toFixed(1)}s` : `${(diff / 60).toFixed(1)}m`;
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

export default function LiveMonitor({ initialRows, initialWallet }: { initialRows: any[]; initialWallet: WalletInfo | null }) {
  const [rows, setRows] = useState<any[]>(initialRows);
  const [wallet, setWallet] = useState<WalletInfo | null>(initialWallet);
  const [liveConfig, setLiveConfig] = useState<LiveConfig | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());
  const [now, setNow] = useState<Date>(new Date());
  const [error, setError] = useState<string | null>(null);
  const [markingId, setMarkingId] = useState<number | null>(null);
  const [history, setHistory] = useState<WalletHistory | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  async function loadHistory() {
    setHistoryLoading(true);
    try {
      const h = await getWalletHistory(50);
      setHistory(h);
    } catch (e: any) {
      setHistory({ pubkey: null, trades: [], error: e.message });
    } finally {
      setHistoryLoading(false);
    }
  }

  async function handleMarkSold(id: number) {
    setMarkingId(id);
    try {
      await markCallSold(id);
      await refresh();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setMarkingId(null);
    }
  }

  const refresh = useCallback(async () => {
    try {
      const [queueRes, walletData, configData] = await Promise.all([
        fetch("/api/live/queue?limit=100", { cache: "no-store" }),
        getWallet().catch(() => null),
        getLiveConfig().catch(() => null),
      ]);
      if (!queueRes.ok) throw new Error(`HTTP ${queueRes.status}`);
      const data = await queueRes.json();
      setRows(data);
      setWallet(walletData);
      setLiveConfig(configData);
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

  const S = {
    card:    { padding: 20, background: "#f8faff", border: "1px solid #dbeafe", borderRadius: 12 } as const,
    cardDark:{ padding: 20, background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12 } as const,
    label:   { fontSize: 11, color: "#6b7280", textTransform: "uppercase" as const, letterSpacing: "0.06em", marginBottom: 2 },
    stat:    { fontSize: 26, fontWeight: 700, letterSpacing: "-0.5px", lineHeight: 1 } as const,
  };

  return (
    <div>
      {/* Wallet stat cards — live-updating */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 14, marginBottom: 20 }}>
        <div style={S.card}>
          <div style={S.label}>Wallet balance</div>
          <div style={S.stat}>
            {wallet?.sol_balance != null ? `${wallet.sol_balance}` : "—"}
            <span style={{ fontSize: 14, fontWeight: 400, color: "#6b7280" }}> SOL</span>
          </div>
          {wallet?.pubkey && (
            <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 4, fontFamily: "monospace" }}>
              {wallet.pubkey.slice(0, 8)}…{wallet.pubkey.slice(-8)}
            </div>
          )}
        </div>
        <div style={S.cardDark}>
          <div style={S.label}>Buys sent</div>
          <div style={S.stat}>{wallet?.total_buys ?? "—"}</div>
        </div>
        <div style={S.cardDark}>
          <div style={S.label}>Sells sent</div>
          <div style={S.stat}>{wallet?.total_sells ?? "—"}</div>
        </div>
        <div style={{ ...S.cardDark, borderColor: wallet?.holding ? "#fde68a" : undefined, background: wallet?.holding ? "#fffbeb" : undefined }}>
          <div style={S.label}>Currently holding</div>
          <div style={{ ...S.stat, color: wallet?.holding ? "#d97706" : undefined }}>
            {wallet?.holding ?? "—"}
          </div>
        </div>
      </div>

      {/* Live Channels Configuration */}
      {wallet?.live_channels && wallet.live_channels.length > 0 && (() => {
        const skMatch = liveConfig?.live_strategy_key?.match(/^tp(\d+)_sl(\d+)$/);
        const fallbackTp = skMatch ? Number(skMatch[1]) : null;
        const fallbackSl = skMatch ? Number(skMatch[2]) : null;
        return (
          <div style={{ marginBottom: 20, padding: "14px 18px", background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 10 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "#15803d", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 10 }}>
              Live Channels ({wallet.live_channels.length})
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
              {wallet.live_channels.map((ch) => {
                const tp = ch.live_tp_pct ?? fallbackTp;
                const sl = ch.live_sl_pct ?? fallbackSl;
                return (
                  <div key={ch.id} style={{ padding: "8px 14px", background: "#fff", border: "1px solid #bbf7d0", borderRadius: 8, fontSize: 12 }}>
                    <div style={{ fontWeight: 700, color: "#15803d", marginBottom: 4 }}>@{ch.telegram_username}</div>
                    <div style={{ color: "#374151" }}>
                      <span style={{ color: "#16a34a", fontWeight: 600 }}>TP +{tp ?? "?"}%</span>
                      {" / "}
                      <span style={{ color: "#dc2626", fontWeight: 600 }}>SL -{sl ?? "?"}%</span>
                    </div>
                    <div style={{ color: "#6b7280", marginTop: 2 }}>
                      {ch.live_buy_amount_sol != null ? `${ch.live_buy_amount_sol} SOL / trade` : "amount: env default"}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })()}

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
                <th style={{ textAlign: "left" }}>TP/SL</th>
                <th style={{ textAlign: "left" }}>Mint</th>
                <th style={{ textAlign: "left" }}>Signal→Buy</th>
                <th style={{ textAlign: "left" }}>Holding</th>
                <th style={{ textAlign: "left" }}>Amount</th>
                <th style={{ textAlign: "left" }}>Sell status</th>
                <th style={{ textAlign: "left" }}>Outcome</th>
                <th style={{ textAlign: "left" }}>Signal at</th>
                <th style={{ textAlign: "left" }}></th>
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
                const skMatch = typeof r.strategy_key === "string" ? r.strategy_key.match(/^tp(\d+)_sl(\d+)$/) : null;
                const tp = skMatch ? Number(skMatch[1]) : (r.live_tp_pct ?? null);
                const sl = skMatch ? Number(skMatch[2]) : (r.live_sl_pct ?? null);
                return (
                  <tr key={r.id} style={{ borderBottom: "1px solid #fef3c7" }}>
                    <td><a href={`/calls/${r.id}`} style={{ textDecoration: "underline" }}>{r.id}</a></td>
                    <td><b>{r.channel_key}</b></td>
                    <td style={{ fontSize: 11 }}>
                      {tp != null ? <span style={{ color: "#16a34a", fontWeight: 600 }}>TP +{tp}%</span> : "—"}
                      {tp != null && sl != null && " / "}
                      {sl != null ? <span style={{ color: "#dc2626", fontWeight: 600 }}>SL -{sl}%</span> : ""}
                    </td>
                    <td style={{ fontFamily: "monospace", fontSize: 11 }}>
                      {r.mint ? (
                        <a href={gmgnSolanaTokenUrl(r.mint)} target="_blank" rel="noreferrer" style={{ color: "#1d4ed8" }}>
                          {String(r.mint).slice(0, 12)}…
                        </a>
                      ) : ""}
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
                    <td>
                      <button
                        onClick={() => handleMarkSold(r.id)}
                        disabled={markingId === r.id}
                        style={{ padding: "3px 10px", borderRadius: 6, fontSize: 11, fontWeight: 600, background: "#fee2e2", color: "#b91c1c", border: "1px solid #fecaca", cursor: "pointer" }}
                      >
                        {markingId === r.id ? "…" : "Mark sold"}
                      </button>
                    </td>
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
                <th style={{ textAlign: "left" }}>TP/SL</th>
                <th style={{ textAlign: "left" }}>Amount</th>
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
                const pendingTp = r.live_tp_pct ?? null;
                const pendingSl = r.live_sl_pct ?? null;
                const effectiveAmount = r.live_buy_amount_sol ?? r.channel_buy_amount_sol ?? null;
                return (
                  <tr key={r.id} style={{ borderBottom: "1px solid #dbeafe" }}>
                    <td><a href={`/calls/${r.id}`} style={{ textDecoration: "underline" }}>{r.id}</a></td>
                    <td><b>{r.channel_key}</b></td>
                    <td style={{ fontSize: 11 }}>
                      {pendingTp != null ? <span style={{ color: "#16a34a", fontWeight: 600 }}>TP +{pendingTp}%</span> : "—"}
                      {pendingTp != null && pendingSl != null && " / "}
                      {pendingSl != null ? <span style={{ color: "#dc2626", fontWeight: 600 }}>SL -{pendingSl}%</span> : ""}
                    </td>
                    <td>{effectiveAmount != null ? `${effectiveAmount} SOL` : "—"}</td>
                    <td style={{ fontFamily: "monospace", fontSize: 11 }}>
                      {r.mint ? (
                        <a href={gmgnSolanaTokenUrl(r.mint)} target="_blank" rel="noreferrer" style={{ color: "#1d4ed8" }}>
                          {String(r.mint).slice(0, 12)}…
                        </a>
                      ) : ""}
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

      {/* ── On-Chain Wallet History (Helius) ── */}
      <section style={{ marginBottom: 32, borderTop: "2px solid #e5e7eb", paddingTop: 24 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 12 }}>
          <h3 style={{ margin: 0, color: "#1d4ed8" }}>On-Chain Swap History</h3>
          <button
            onClick={loadHistory}
            disabled={historyLoading}
            style={{ padding: "5px 14px", borderRadius: 7, fontSize: 12, fontWeight: 600, background: "#dbeafe", color: "#1d4ed8", border: "1px solid #bfdbfe", cursor: "pointer" }}
          >
            {historyLoading ? "Loading…" : history ? "Refresh" : "Load from Helius"}
          </button>
          {history?.pubkey && (
            <span style={{ fontSize: 11, color: "#9ca3af", fontFamily: "monospace" }}>
              {history.pubkey.slice(0, 8)}…{history.pubkey.slice(-8)}
            </span>
          )}
        </div>

        {!history && !historyLoading && (
          <p style={{ color: "#9ca3af", fontSize: 13 }}>
            Fetches real on-chain swaps from the Solana RPC and matches them against bot calls by mint address.
            Requires <code>SOLANA_PRIVATE_KEY</code> to be set (used to derive the wallet address).
          </p>
        )}

        {history?.error && (
          <div style={{ padding: "10px 14px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, color: "#b91c1c", fontSize: 13, marginBottom: 12 }}>
            Error: {history.error}
          </div>
        )}

        {history && !history.error && history.trades.length === 0 && (
          <p style={{ color: "#9ca3af", fontSize: 13 }}>No swap transactions found for this wallet.</p>
        )}

        {history && history.trades.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table cellPadding={8} style={{ borderCollapse: "collapse", width: "100%", fontSize: 12 }}>
              <thead>
                <tr style={{ background: "#f0f9ff", borderBottom: "2px solid #bae6fd" }}>
                  <th style={{ textAlign: "left", padding: "8px 10px" }}>Time (JST)</th>
                  <th style={{ textAlign: "left", padding: "8px 10px" }}>Direction</th>
                  <th style={{ textAlign: "left", padding: "8px 10px" }}>Mint</th>
                  <th style={{ textAlign: "left", padding: "8px 10px" }}>SOL amount</th>
                  <th style={{ textAlign: "left", padding: "8px 10px" }}>DEX</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", background: "#f0fdf4" }}>Bot call</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", background: "#f0fdf4" }}>Bot buy</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", background: "#eff6ff" }}>Paper TP/SL</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", background: "#eff6ff" }}>Paper PnL</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", background: "#fdf4ff" }}>Real PnL</th>
                  <th style={{ textAlign: "left", padding: "8px 10px" }}>Tx</th>
                </tr>
              </thead>
              <tbody>
                {history.trades.map((t: OnChainTrade, i: number) => {
                  const ts = t.timestamp ? new Date(t.timestamp * 1000) : null;
                  const timeStr = ts ? ts.toLocaleString("ja-JP", { timeZone: "Asia/Tokyo", hour12: false }) : "—";
                  const isBuy = t.direction === "BUY";
                  const isSell = t.direction === "SELL";
                  const call = t.call;
                  const skMatch = call?.strategy_key?.match(/^tp(\d+)_sl(\d+)$/);
                  const tp = skMatch ? Number(skMatch[1]) : 35;
                  const sl = skMatch ? Number(skMatch[2]) : 20;
                  const hasMatch = !!call;
                  return (
                    <tr key={i} style={{ borderBottom: "1px solid #f0f0f0", background: hasMatch ? "#f0fdf4" : "#fff" }}>
                      <td style={{ padding: "8px 10px", fontSize: 11, color: "#555", whiteSpace: "nowrap" }}>{timeStr}</td>
                      <td style={{ padding: "8px 10px", fontWeight: 700, color: isBuy ? "#16a34a" : isSell ? "#dc2626" : "#888" }}>
                        {t.direction || "—"}
                      </td>
                      <td style={{ padding: "8px 10px", fontFamily: "monospace", fontSize: 11 }}>
                        {t.mint ? (
                          <a href={gmgnSolanaTokenUrl(t.mint)} target="_blank" rel="noreferrer" style={{ color: "#1d4ed8" }}>
                            {t.mint.slice(0, 10)}…
                          </a>
                        ) : "—"}
                      </td>
                      <td style={{ padding: "8px 10px", fontWeight: 600, color: isBuy ? "#dc2626" : isSell ? "#16a34a" : "#888" }}>
                        {t.sol_amount != null ? `${isBuy ? "-" : "+"}${t.sol_amount} SOL` : "—"}
                      </td>
                      <td style={{ padding: "8px 10px", fontSize: 11, color: "#6b7280" }}>{t.dex || "—"}</td>
                      <td style={{ padding: "8px 10px", background: "#f0fdf4" }}>
                        {call ? (
                          <a href={`/calls/${call.id}`} style={{ textDecoration: "underline", fontWeight: 600 }}>
                            #{call.id} {call.symbol || ""}
                          </a>
                        ) : <span style={{ color: "#9ca3af" }}>no match</span>}
                      </td>
                      <td style={{ padding: "8px 10px", background: "#f0fdf4", fontSize: 11 }}>
                        {call ? (
                          <>
                            <span style={{ color: call.live_buy_status === "SENT" ? "#16a34a" : "#d97706", fontWeight: 600 }}>
                              {call.live_buy_status}
                            </span>
                            {call.live_buy_amount_sol != null && (
                              <span style={{ color: "#9ca3af" }}> {call.live_buy_amount_sol} SOL</span>
                            )}
                          </>
                        ) : "—"}
                      </td>
                      <td style={{ padding: "8px 10px", background: "#eff6ff", fontSize: 11 }}>
                        {call ? (
                          <>
                            <span style={{ color: "#16a34a", fontWeight: 600 }}>TP +{tp}%</span>
                            {" / "}
                            <span style={{ color: "#dc2626", fontWeight: 600 }}>SL -{sl}%</span>
                            <div style={{ color: "#9ca3af", fontSize: 10 }}>{call.strategy_key}</div>
                          </>
                        ) : "—"}
                      </td>
                      <td style={{ padding: "8px 10px", background: "#eff6ff", fontWeight: 600, color: (call?.pnl_pct ?? 0) >= 0 ? "#16a34a" : "#dc2626" }}>
                        {call?.pnl_pct != null
                          ? `${Number(call.pnl_pct) >= 0 ? "+" : ""}${Number(call.pnl_pct).toFixed(1)}% (${call.outcome})`
                          : call ? "pending" : "—"}
                      </td>
                      <td style={{ padding: "8px 10px", background: "#fdf4ff", fontWeight: 600 }}>
                        {(() => {
                          if (t.direction !== "SELL") return <span style={{ color: "#9ca3af" }}>—</span>;
                          const buySol = call?.live_buy_amount_sol;
                          const sellSol = t.sol_amount;
                          if (!buySol || !sellSol) return <span style={{ color: "#9ca3af" }}>—</span>;
                          const realPnl = ((sellSol - buySol) / buySol) * 100;
                          return (
                            <span style={{ color: realPnl >= 0 ? "#16a34a" : "#dc2626" }}>
                              {realPnl >= 0 ? "+" : ""}{realPnl.toFixed(1)}%
                            </span>
                          );
                        })()}
                      </td>
                      <td style={{ padding: "8px 10px" }}>
                        {t.signature ? (
                          <a
                            href={`https://solscan.io/tx/${t.signature}`}
                            target="_blank"
                            rel="noreferrer"
                            style={{ fontSize: 11, color: "#6366f1" }}
                          >
                            solscan
                          </a>
                        ) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── Completed — Real vs Paper Analysis ── */}
      <section>
        {/* Summary row */}
        {recent.length > 0 && (() => {
          const liveTP  = recent.filter((r) => r.live_sell_reason === "TP").length;
          const liveSL  = recent.filter((r) => r.live_sell_reason === "SL").length;
          const liveErr = recent.filter((r) => r.live_sell_status === "ERROR").length;
          const paperTP = recent.filter((r) => r.outcome === "TP").length;
          const paperSL = recent.filter((r) => r.outcome === "SL").length;
          const paperPnl = recent.reduce((s: number, r: any) => s + (r.pnl_pct != null ? Number(r.pnl_pct) : 0), 0);
          const avgPaperPnl = recent.length ? paperPnl / recent.length : 0;
          return (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 10, marginBottom: 14 }}>
              <div style={{ padding: "10px 14px", background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10 }}>
                <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.05em" }}>Live TP hits</div>
                <div style={{ fontSize: 22, fontWeight: 700, color: "#16a34a" }}>{liveTP}</div>
              </div>
              <div style={{ padding: "10px 14px", background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10 }}>
                <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.05em" }}>Live SL hits</div>
                <div style={{ fontSize: 22, fontWeight: 700, color: "#dc2626" }}>{liveSL}</div>
              </div>
              <div style={{ padding: "10px 14px", background: "#fff", border: "1px solid #e5e7eb", borderRadius: 10 }}>
                <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.05em" }}>Errors</div>
                <div style={{ fontSize: 22, fontWeight: 700, color: "#d97706" }}>{liveErr}</div>
              </div>
              <div style={{ padding: "10px 14px", background: "#f8faff", border: "1px solid #dbeafe", borderRadius: 10 }}>
                <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.05em" }}>Paper TP / SL</div>
                <div style={{ fontSize: 16, fontWeight: 700 }}>
                  <span style={{ color: "#16a34a" }}>{paperTP}↑</span>
                  {" / "}
                  <span style={{ color: "#dc2626" }}>{paperSL}↓</span>
                </div>
              </div>
              <div style={{ padding: "10px 14px", background: "#f8faff", border: "1px solid #dbeafe", borderRadius: 10 }}>
                <div style={{ fontSize: 10, color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.05em" }}>Avg paper PnL</div>
                <div style={{ fontSize: 22, fontWeight: 700, color: avgPaperPnl >= 0 ? "#16a34a" : "#dc2626" }}>
                  {avgPaperPnl >= 0 ? "+" : ""}{avgPaperPnl.toFixed(1)}%
                </div>
              </div>
            </div>
          );
        })()}

        <h3 style={{ margin: "0 0 8px", color: "#444" }}>
          Completed — Real vs Paper ({recent.length})
        </h3>
        {recent.length === 0 ? (
          <p style={{ color: "#999", fontSize: 13 }}>No completed trades yet.</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table cellPadding={8} style={{ borderCollapse: "collapse", width: "100%", fontSize: 12 }}>
              <thead>
                <tr style={{ background: "#f8f8f8", borderBottom: "2px solid #e5e7eb" }}>
                  <th style={{ textAlign: "left", padding: "8px 10px" }}>ID</th>
                  <th style={{ textAlign: "left", padding: "8px 10px" }}>Channel</th>
                  <th style={{ textAlign: "left", padding: "8px 10px" }}>Mint</th>
                  <th style={{ textAlign: "left", padding: "8px 10px" }}>Configured TP/SL</th>
                  <th style={{ textAlign: "left", padding: "8px 10px" }}>Amount</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", background: "#f0fdf4" }}>Live trigger</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", background: "#f0fdf4" }}>Live sell</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", background: "#eff6ff" }}>Paper outcome</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", background: "#eff6ff" }}>Paper PnL</th>
                  <th style={{ textAlign: "left", padding: "8px 10px" }}>Held</th>
                  <th style={{ textAlign: "left", padding: "8px 10px" }}>Error</th>
                  <th style={{ textAlign: "left", padding: "8px 10px" }}>Signal at</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((r) => {
                  const liveTrigger = r.live_sell_reason;
                  const paperOutcome = r.outcome;
                  // Discrepancy: live and paper disagree (e.g. live triggered SL but paper says TP would have hit)
                  const discrepancy = liveTrigger && paperOutcome && liveTrigger !== paperOutcome;
                  // Parse TP/SL from actual strategy_key (e.g. "tp55_sl20" → tp=55, sl=20)
                  // Fall back to channel settings, then to env defaults
                  const skMatch = typeof r.strategy_key === "string"
                    ? r.strategy_key.match(/^tp(\d+)_sl(\d+)$/)
                    : null;
                  const tp = skMatch ? Number(skMatch[1]) : (r.live_tp_pct ?? 35);
                  const sl = skMatch ? Number(skMatch[2]) : (r.live_sl_pct ?? 20);
                  const entryUsd = r.entry_price_usd;
                  const tpPrice = entryUsd != null ? (entryUsd * (1 + tp / 100)) : null;
                  const slPrice = entryUsd != null ? (entryUsd * (1 - sl / 100)) : null;
                  return (
                    <tr
                      key={r.id}
                      style={{ borderBottom: "1px solid #f0f0f0", background: discrepancy ? "#fffbeb" : "#fff" }}
                    >
                      <td style={{ padding: "8px 10px" }}>
                        <a href={`/calls/${r.id}`} style={{ textDecoration: "underline" }}>{r.id}</a>
                        {discrepancy && <span style={{ marginLeft: 4, fontSize: 10, background: "#fef3c7", color: "#92400e", padding: "1px 4px", borderRadius: 4 }}>⚠ mismatch</span>}
                      </td>
                      <td style={{ padding: "8px 10px" }}><b>{r.channel_key}</b></td>
                      <td style={{ padding: "8px 10px", fontFamily: "monospace", fontSize: 11 }}>
                        {r.mint ? (
                          <a href={gmgnSolanaTokenUrl(r.mint)} target="_blank" rel="noreferrer" style={{ color: "#1d4ed8" }}>
                            {String(r.mint).slice(0, 10)}…
                          </a>
                        ) : ""}
                      </td>
                      <td style={{ padding: "8px 10px", fontSize: 11 }}>
                        <span style={{ color: "#16a34a", fontWeight: 600 }}>TP +{tp}%</span>
                        {tpPrice != null && <span style={{ color: "#9ca3af" }}> (${tpPrice.toFixed(8)})</span>}
                        <br />
                        <span style={{ color: "#dc2626", fontWeight: 600 }}>SL -{sl}%</span>
                        {slPrice != null && <span style={{ color: "#9ca3af" }}> (${slPrice.toFixed(8)})</span>}
                        {r.strategy_key && (
                          <div style={{ color: "#9ca3af", fontSize: 10, marginTop: 2 }}>{r.strategy_key}</div>
                        )}
                      </td>
                      <td style={{ padding: "8px 10px", fontSize: 11 }}>
                        {(r.live_buy_amount_sol ?? r.channel_buy_amount_sol) != null
                          ? `${r.live_buy_amount_sol ?? r.channel_buy_amount_sol} SOL`
                          : "—"}
                      </td>
                      <td style={{ padding: "8px 10px", background: "#f0fdf4" }}>
                        <span style={{
                          fontWeight: 700, fontSize: 12,
                          color: liveTrigger === "TP" ? "#16a34a" : liveTrigger === "SL" ? "#dc2626" : "#888",
                        }}>
                          {liveTrigger || "—"}
                        </span>
                      </td>
                      <td style={{ padding: "8px 10px", background: "#f0fdf4" }}>
                        {statusBadge(r.live_sell_status)}
                      </td>
                      <td style={{ padding: "8px 10px", background: "#eff6ff" }}>
                        <span style={{ color: outcomeColor(paperOutcome), fontWeight: 700 }}>
                          {paperOutcome || "—"}
                        </span>
                      </td>
                      <td style={{ padding: "8px 10px", background: "#eff6ff", fontWeight: 600, color: (r.pnl_pct ?? 0) >= 0 ? "#16a34a" : "#dc2626" }}>
                        {r.pnl_pct != null ? `${Number(r.pnl_pct) >= 0 ? "+" : ""}${Number(r.pnl_pct).toFixed(1)}%` : "—"}
                      </td>
                      <td style={{ padding: "8px 10px" }}>{secDiff(r.live_buy_sent_at, r.live_sell_sent_at)}</td>
                      <td style={{ padding: "8px 10px", color: "crimson", fontSize: 11, maxWidth: 140 }}>
                        {r.live_buy_error || r.live_sell_error
                          ? String(r.live_buy_error || r.live_sell_error).slice(0, 60)
                          : ""}
                      </td>
                      <td style={{ padding: "8px 10px", fontSize: 11, color: "#666" }}>{toJST(r.started_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
