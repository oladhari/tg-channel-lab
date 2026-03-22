"use client";

import { useEffect, useState, useCallback } from "react";
import { getChannels, getExplorer, getBestStrategy } from "../../lib/api";
import type { Channel, ExplorerRow, StrategyExplorer, GridCell } from "../../lib/api";
import { gmgnSolanaTokenUrl } from "../../lib/links";
import { toJST } from "../../lib/time";

// ── Styles ────────────────────────────────────────────────────────────────────
const S = {
  page:  { padding: "24px 28px 48px", fontFamily: "system-ui, sans-serif", maxWidth: 1200, margin: "0 auto" } as const,
  th:    { padding: "10px 12px", textAlign: "left" as const, fontSize: 12, color: "#6b7280", textTransform: "uppercase" as const, letterSpacing: "0.05em", borderBottom: "1px solid #e5e7eb", whiteSpace: "nowrap" as const },
  td:    { padding: "11px 12px", fontSize: 13, borderBottom: "1px solid #f3f4f6", verticalAlign: "middle" as const },
  badge: (color: string) => ({ display: "inline-block", padding: "2px 8px", borderRadius: 6, fontSize: 11, fontWeight: 600, background: color + "18", color }) as const,
  input: { padding: "7px 11px", border: "1px solid #d1d5db", borderRadius: 8, fontSize: 13, width: 80, outline: "none" } as const,
  select:{ padding: "7px 11px", border: "1px solid #d1d5db", borderRadius: 8, fontSize: 13, minWidth: 160, outline: "none", background: "#fff" } as const,
  btn:   { padding: "8px 18px", borderRadius: 8, background: "#1d4ed8", color: "#fff", border: "none", fontSize: 13, fontWeight: 600, cursor: "pointer" } as const,
};

function shortMint(m: string) {
  return `${m.slice(0, 6)}…${m.slice(-6)}`;
}

function fmtDuration(sec: number | null) {
  if (sec == null) return "—";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

// ── Summary bar ───────────────────────────────────────────────────────────────
function Summary({ rows }: { rows: ExplorerRow[] }) {
  if (rows.length === 0) return null;
  const tp   = rows.filter((r) => r.outcome === "TP").length;
  const sl   = rows.filter((r) => r.outcome === "SL").length;
  const time = rows.filter((r) => r.outcome === "TIME").length;
  const avgPnl = rows.reduce((s, r) => s + r.pnl_pct, 0) / rows.length;
  const winRate = (tp / rows.length) * 100;

  const cardStyle = { padding: "14px 18px", border: "1px solid #e5e7eb", borderRadius: 10, background: "#fff", minWidth: 110 };
  const lbl = { fontSize: 11, color: "#6b7280", textTransform: "uppercase" as const, letterSpacing: "0.06em", marginBottom: 4 };
  const val = { fontSize: 22, fontWeight: 700, letterSpacing: "-0.5px" };

  return (
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 20 }}>
      <div style={cardStyle}><div style={lbl}>Calls</div><div style={val}>{rows.length}</div></div>
      <div style={{ ...cardStyle, borderColor: "#bbf7d0" }}><div style={lbl}>TP</div><div style={{ ...val, color: "#16a34a" }}>{tp}</div></div>
      <div style={{ ...cardStyle, borderColor: "#fecaca" }}><div style={lbl}>SL</div><div style={{ ...val, color: "#dc2626" }}>{sl}</div></div>
      <div style={{ ...cardStyle, borderColor: "#fed7aa" }}><div style={lbl}>TIME</div><div style={{ ...val, color: "#d97706" }}>{time}</div></div>
      <div style={cardStyle}><div style={lbl}>Win Rate</div><div style={{ ...val, color: winRate >= 50 ? "#16a34a" : "#dc2626" }}>{winRate.toFixed(1)}%</div></div>
      <div style={cardStyle}><div style={lbl}>Avg PnL</div><div style={{ ...val, color: avgPnl >= 0 ? "#16a34a" : "#dc2626" }}>{avgPnl >= 0 ? "+" : ""}{avgPnl.toFixed(2)}%</div></div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function ExplorerPage() {
  const [channels, setChannels]         = useState<Channel[]>([]);
  const [channelKey, setChannelKey]     = useState("");
  const [tp, setTp]                     = useState("35");
  const [sl, setSl]                     = useState("20");
  const [rows, setRows]                 = useState<ExplorerRow[] | null>(null);
  const [loading, setLoading]           = useState(false);
  const [error, setError]               = useState<string | null>(null);
  const [best, setBest]                 = useState<StrategyExplorer | null>(null);
  const [bestLoading, setBestLoading]   = useState(false);
  const [bestError, setBestError]       = useState<string | null>(null);
  const [rankingMode, setRankingMode]   = useState<"pnl" | "risk_adjusted">("pnl");

  // Load channels once on mount
  useEffect(() => {
    getChannels().then((chs) => {
      setChannels(chs);
      if (chs.length > 0) setChannelKey(chs[0].key);
    }).catch(() => {});
  }, []);

  const run = useCallback(async () => {
    if (!channelKey) return;
    const tpNum = parseFloat(tp);
    const slNum = parseFloat(sl);
    if (!isFinite(tpNum) || tpNum <= 0 || !isFinite(slNum) || slNum <= 0 || slNum >= 100) {
      setError("TP must be > 0 and SL must be between 0 and 100.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await getExplorer({ channel_key: channelKey, tp_pct: tpNum, sl_pct: slNum });
      setRows(data);
    } catch (e: any) {
      setError(e?.message ?? "Request failed");
      setRows(null);
    } finally {
      setLoading(false);
    }
  }, [channelKey, tp, sl]);

  const runBest = useCallback(async () => {
    if (!channelKey) return;
    setBestLoading(true);
    setBestError(null);
    try {
      const data = await getBestStrategy({ channel_key: channelKey, ranking_mode: rankingMode });
      setBest(data);
    } catch (e: any) {
      setBestError(e?.message ?? "Request failed");
      setBest(null);
    } finally {
      setBestLoading(false);
    }
  }, [channelKey, rankingMode]);

  // Auto-run when channel changes (if we already have a valid TP/SL)
  useEffect(() => {
    if (channelKey && rows !== null) run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channelKey]);

  return (
    <main style={S.page}>
      {/* Header */}
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: "0 0 4px" }}>Calls Explorer</h1>
        <p style={{ margin: 0, color: "#6b7280", fontSize: 13 }}>
          Simulate any TP / SL on every recorded call for a channel — first-hit-wins.
        </p>
      </div>

      {/* Controls */}
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 24, padding: "14px 16px", background: "#f9fafb", border: "1px solid #e5e7eb", borderRadius: 10 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <label style={{ fontSize: 11, color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.05em" }}>Channel</label>
          <select
            style={S.select}
            value={channelKey}
            onChange={(e) => setChannelKey(e.target.value)}
          >
            {channels.length === 0 && <option value="">Loading…</option>}
            {channels.map((c) => (
              <option key={c.key} value={c.key}>{c.key}</option>
            ))}
          </select>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <label style={{ fontSize: 11, color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.05em" }}>TP %</label>
          <input
            type="number"
            min={1}
            max={10000}
            step={5}
            style={S.input}
            value={tp}
            onChange={(e) => setTp(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && run()}
          />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <label style={{ fontSize: 11, color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.05em" }}>SL %</label>
          <input
            type="number"
            min={1}
            max={99}
            step={5}
            style={S.input}
            value={sl}
            onChange={(e) => setSl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && run()}
          />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <label style={{ fontSize: 11, color: "transparent", userSelect: "none" }}>_</label>
          <button style={{ ...S.btn, opacity: loading ? 0.6 : 1 }} onClick={run} disabled={loading}>
            {loading ? "Loading…" : "Apply"}
          </button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <label style={{ fontSize: 11, color: "#6b7280", textTransform: "uppercase", letterSpacing: "0.05em" }}>Ranking</label>
          <select
            style={{ ...S.select, minWidth: 140 }}
            value={rankingMode}
            onChange={(e) => setRankingMode(e.target.value as "pnl" | "risk_adjusted")}
          >
            <option value="pnl">Highest PnL</option>
            <option value="risk_adjusted">Risk-adjusted</option>
          </select>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          <label style={{ fontSize: 11, color: "transparent", userSelect: "none" }}>_</label>
          <button
            style={{ ...S.btn, opacity: bestLoading ? 0.6 : 1, background: "#6d28d9" }}
            onClick={runBest}
            disabled={bestLoading}
          >
            {bestLoading ? "Scanning…" : "Find Best Strategy"}
          </button>
        </div>

        {rows !== null && !loading && (
          <div style={{ marginLeft: "auto", fontSize: 12, color: "#9ca3af", alignSelf: "flex-end", paddingBottom: 2 }}>
            {rows.length} calls · TP {tp}% / SL {sl}%
          </div>
        )}
      </div>

      {/* Best Strategy Panel */}
      {bestError && (
        <div style={{ marginBottom: 16, padding: "10px 14px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, color: "#b91c1c", fontSize: 13 }}>
          {bestError}
        </div>
      )}
      {best && (
        <div style={{ marginBottom: 24, border: "1px solid #ddd6fe", borderRadius: 12, background: "#faf5ff", overflow: "hidden" }}>
          {/* Header */}
          <div style={{ padding: "14px 18px", borderBottom: "1px solid #ddd6fe", display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
            <div>
              <span style={{ fontSize: 11, color: "#7c3aed", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 600 }}>Best Strategy</span>
              <span style={{ marginLeft: 10, fontSize: 13, color: "#6b7280" }}>{best.n_calls} calls · sorted by {rankingMode === "risk_adjusted" ? "risk-adjusted score" : "avg PnL"}</span>
            </div>
            {best.best_tp_pct != null && best.best_sl_pct != null && (
              <>
                <div style={{ fontWeight: 700, fontSize: 15, color: "#4c1d95" }}>
                  TP {best.best_tp_pct}% / SL {best.best_sl_pct}%
                </div>
                <button
                  style={{ ...S.btn, background: "#7c3aed", fontSize: 12, padding: "5px 14px" }}
                  onClick={() => { setTp(String(best.best_tp_pct)); setSl(String(best.best_sl_pct)); }}
                >
                  Apply to inputs
                </button>
              </>
            )}
            {best.best_tp_pct == null && (
              <span style={{ fontSize: 13, color: "#9ca3af" }}>No calls found</span>
            )}
          </div>

          {/* Top-10 ranked combos */}
          {best.all_results.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              <table cellPadding={0} style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
                <thead>
                  <tr style={{ background: "#ede9fe" }}>
                    <th style={{ ...S.th, color: "#6d28d9" }}>#</th>
                    <th style={{ ...S.th, color: "#6d28d9" }}>TP %</th>
                    <th style={{ ...S.th, color: "#6d28d9" }}>SL %</th>
                    <th style={{ ...S.th, color: "#6d28d9" }}>Trades</th>
                    <th style={{ ...S.th, color: "#6d28d9" }}>Win Rate</th>
                    <th style={{ ...S.th, color: "#6d28d9" }}>Avg PnL</th>
                    <th style={{ ...S.th, color: "#6d28d9" }}>Score</th>
                    <th style={{ ...S.th, color: "#6d28d9" }}>End Balance</th>
                  </tr>
                </thead>
                <tbody>
                  {best.all_results.slice(0, 10).map((r: GridCell, i: number) => {
                    const isBest = r.tp_pct === best.best_tp_pct && r.sl_pct === best.best_sl_pct;
                    return (
                      <tr key={`${r.tp_pct}-${r.sl_pct}`} style={{ background: isBest ? "#ede9fe" : "#fff" }}>
                        <td style={{ ...S.td, color: "#9ca3af", width: 32 }}>{i + 1}</td>
                        <td style={{ ...S.td, fontWeight: isBest ? 700 : 400 }}>{r.tp_pct}%</td>
                        <td style={{ ...S.td, fontWeight: isBest ? 700 : 400 }}>{r.sl_pct}%</td>
                        <td style={S.td}>{r.n_trades}</td>
                        <td style={{ ...S.td, color: r.win_rate_tp_pct >= 50 ? "#16a34a" : "#dc2626" }}>
                          {r.win_rate_tp_pct.toFixed(1)}%
                        </td>
                        <td style={{ ...S.td, fontWeight: 600, color: r.avg_pnl_pct >= 0 ? "#16a34a" : "#dc2626" }}>
                          {r.avg_pnl_pct >= 0 ? "+" : ""}{r.avg_pnl_pct.toFixed(2)}%
                        </td>
                        <td style={{ ...S.td, color: "#6d28d9", fontFamily: "monospace" }}>
                          {r.score != null ? r.score.toFixed(2) : "—"}
                        </td>
                        <td style={{ ...S.td, color: "#374151" }}>{r.end_balance_sol.toFixed(3)} SOL</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{ marginBottom: 16, padding: "10px 14px", background: "#fef2f2", border: "1px solid #fecaca", borderRadius: 8, color: "#b91c1c", fontSize: 13 }}>
          {error}
        </div>
      )}

      {/* Empty state */}
      {rows === null && !loading && (
        <div style={{ padding: "32px 0", textAlign: "center", color: "#9ca3af", fontSize: 13 }}>
          Select a channel and press Apply to simulate.
        </div>
      )}

      {/* Results */}
      {rows !== null && (
        <>
          <Summary rows={rows} />

          <div style={{ overflowX: "auto", border: "1px solid #e5e7eb", borderRadius: 12 }}>
            <table cellPadding={0} style={{ borderCollapse: "collapse", width: "100%" }}>
              <thead style={{ background: "#f9fafb" }}>
                <tr>
                  <th style={S.th}>Mint</th>
                  <th style={S.th}>Entry</th>
                  <th style={S.th}>Outcome</th>
                  <th style={S.th}>PnL %</th>
                  <th style={S.th}>Exit in</th>
                  <th style={S.th}>Exit price</th>
                  <th style={S.th}>Started JST</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={7} style={{ padding: 20, textAlign: "center", color: "#9ca3af", fontSize: 13 }}>
                      No completed calls found for this channel yet.
                    </td>
                  </tr>
                )}
                {rows.map((r) => {
                  const oc = r.outcome;
                  const ocColor = oc === "TP" ? "#16a34a" : oc === "SL" ? "#dc2626" : "#d97706";
                  const pnl = r.pnl_pct;

                  return (
                    <tr key={r.call_id} style={{ background: "#fff" }}>
                      <td style={{ ...S.td, fontFamily: "monospace" }}>
                        <a href={`/calls/${r.call_id}`} style={{ color: "#374151", textDecoration: "none" }}>
                          {shortMint(r.mint)}
                        </a>
                        {" "}
                        <a
                          href={gmgnSolanaTokenUrl(r.mint)}
                          target="_blank"
                          rel="noreferrer"
                          style={{ color: "#9ca3af", fontSize: 11, textDecoration: "none" }}
                        >
                          GMGN
                        </a>
                        {r.symbol ? <span style={{ marginLeft: 6, color: "#9ca3af", fontSize: 11 }}>({r.symbol})</span> : null}
                      </td>

                      <td style={{ ...S.td, fontFamily: "monospace", color: "#6b7280" }}>
                        {r.entry_price_usd != null ? r.entry_price_usd.toFixed(8) : "—"}
                      </td>

                      <td style={S.td}>
                        <span style={S.badge(ocColor)}>{oc}</span>
                      </td>

                      <td style={{ ...S.td, fontWeight: 600, color: pnl >= 0 ? "#16a34a" : "#dc2626" }}>
                        {pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}%
                      </td>

                      <td style={{ ...S.td, color: "#6b7280" }}>
                        {fmtDuration(r.exit_t_sec)}
                      </td>

                      <td style={{ ...S.td, fontFamily: "monospace", color: "#6b7280", fontSize: 12 }}>
                        {r.exit_price_usd != null ? r.exit_price_usd.toFixed(8) : "—"}
                      </td>

                      <td style={{ ...S.td, color: "#9ca3af", fontSize: 12 }}>
                        {toJST(r.started_at)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </main>
  );
}
