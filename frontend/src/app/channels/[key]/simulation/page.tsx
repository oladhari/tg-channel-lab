// frontend/src/app/channels/[key]/simulation/page.tsx
"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState, useEffect } from "react";
import { getGridSim, type GridSim } from "../../../../lib/api";

const DEFAULT_TP = "20,25,30,35,40,45,50,55,60,65,70,75,80,90,100";
const DEFAULT_SL = "10,15,20,25,30,35,40,45,50";

const S = {
  page:    { padding: "24px 28px 48px", fontFamily: "system-ui, sans-serif", maxWidth: 1200, margin: "0 auto" } as const,
  card:    { padding: 20, background: "#f8faff", border: "1px solid #dbeafe", borderRadius: 12 } as const,
  cardDark:{ padding: 20, background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12 } as const,
  label:   { fontSize: 11, color: "#6b7280", textTransform: "uppercase" as const, letterSpacing: "0.06em", marginBottom: 2 },
  stat:    { fontSize: 26, fontWeight: 700, letterSpacing: "-0.5px", lineHeight: 1 } as const,
  th:      { padding: "10px 12px", textAlign: "left" as const, fontSize: 12, color: "#6b7280", textTransform: "uppercase" as const, letterSpacing: "0.05em", borderBottom: "1px solid #e5e7eb", whiteSpace: "nowrap" as const },
  td:      { padding: "11px 12px", fontSize: 13, borderBottom: "1px solid #f3f4f6", verticalAlign: "middle" as const },
  badge:   (color: string) => ({ display: "inline-block", padding: "2px 8px", borderRadius: 6, fontSize: 11, fontWeight: 600, background: color + "18", color }) as const,
  pill:    (ok: boolean) => ({ display: "inline-block", padding: "2px 8px", borderRadius: 20, fontSize: 11, fontWeight: 600, background: ok ? "#dcfce7" : "#fee2e2", color: ok ? "#15803d" : "#b91c1c" }) as const,
};

const inputStyle = { padding: "6px 10px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 13, width: "100%" } as const;
const btnPrimary = { padding: "8px 16px", borderRadius: 8, background: "#1d4ed8", color: "#fff", border: "none", fontWeight: 600, fontSize: 13, cursor: "pointer" } as const;
const btnSecondary = { padding: "8px 16px", borderRadius: 8, background: "#f3f4f6", color: "#374151", border: "1px solid #e5e7eb", fontSize: 13, cursor: "pointer" } as const;

export default function ChannelSimulationPage() {
  const params = useParams<{ key: string }>();
  const channelKey = typeof params?.key === "string" ? params.key : "";

  const [tpValues, setTpValues] = useState(DEFAULT_TP);
  const [slValues, setSlValues] = useState(DEFAULT_SL);
  const [start, setStart] = useState(1.0);
  const [entry, setEntry] = useState(0.1);

  const [accurate, setAccurate] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [data, setData] = useState<GridSim | null>(null);
  const [bestStat, setBestStat] = useState<any>(null);

  useEffect(() => {
    if (!channelKey) return;
    fetch(`/api/stats/best?start_balance_sol=1&entry_sol=0.1`)
      .then((r) => r.json())
      .then((arr: any[]) => {
        const found = arr.find((s) => s.key === channelKey);
        setBestStat(found ?? null);
      })
      .catch(() => null);
  }, [channelKey]);

  async function run() {
    if (!channelKey) return;

    setLoading(true);
    setErr(null);
    try {
      const res = await getGridSim({
        channel_key: channelKey,
        tp_values: tpValues,
        sl_values: slValues,
        start_balance_sol: start,
        entry_sol: entry,
        accurate,
      });
      setData(res);
    } catch (e: any) {
      setErr(e?.message || String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  if (!channelKey) {
    return (
      <main style={S.page}>
        <p style={{ marginTop: 0 }}>
          <Link href="/channels" style={{ textDecoration: "underline" }}>
            ← Back
          </Link>
        </p>
        <h1 style={{ marginBottom: 6 }}>Simulation</h1>
        <p style={{ color: "crimson" }}>Missing channel key in URL.</p>
      </main>
    );
  }

  return (
    <main style={S.page}>
      {/* Breadcrumb */}
      <div style={{ fontSize: 12, color: "#9ca3af", marginBottom: 12 }}>
        <Link href="/" style={{ color: "#6b7280", textDecoration: "none" }}>Dashboard</Link>
        <span style={{ margin: "0 6px" }}>/</span>
        <Link href={`/channels/${channelKey}`} style={{ color: "#6b7280", textDecoration: "none" }}>{channelKey}</Link>
        <span style={{ margin: "0 6px" }}>/</span>
        <span style={{ color: "#374151" }}>Simulation</span>
      </div>

      <h1 style={{ fontSize: 22, fontWeight: 700, margin: "0 0 4px" }}>Simulation: {channelKey}</h1>
      <p style={{ marginTop: 0, marginBottom: 16, color: "#6b7280", fontSize: 13 }}>
        Run a TP/SL grid on stored <code>price_points</code>. No Telegram involved.
      </p>

      {/* Best strategy hint card */}
      {bestStat && (
        <div style={{ background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 10, padding: "12px 16px", marginBottom: 16 }}>
          <span style={{ fontSize: 13, color: "#1e40af" }}>
            Recommended based on grid analysis: <b>TP {bestStat.best_tp_pct}% / SL {bestStat.best_sl_pct}%</b>
            {" → "}<b>{Number(bestStat.end_balance_sol).toFixed(2)} SOL</b> end balance
            {" "}({bestStat.n_trades} trades, {Number(bestStat.win_rate_tp_pct).toFixed(1)}% win rate)
          </span>
        </div>
      )}

      {/* Controls */}
      <div style={{ ...S.cardDark, marginBottom: 20 }}>
        <h3 style={{ marginTop: 0, marginBottom: 12, fontSize: 15, fontWeight: 600 }}>Controls</h3>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(240px, 1fr))", gap: 12 }}>
          <label style={{ display: "grid", gap: 6 }}>
            <span style={{ fontSize: 12, color: "#6b7280" }}>TP values (CSV)</span>
            <input style={inputStyle} value={tpValues} onChange={(e) => setTpValues(e.target.value)} />
          </label>

          <label style={{ display: "grid", gap: 6 }}>
            <span style={{ fontSize: 12, color: "#6b7280" }}>SL values (CSV)</span>
            <input style={inputStyle} value={slValues} onChange={(e) => setSlValues(e.target.value)} />
          </label>

          <label style={{ display: "grid", gap: 6 }}>
            <span style={{ fontSize: 12, color: "#6b7280" }}>Start balance (SOL)</span>
            <input
              style={inputStyle}
              type="number"
              step="0.01"
              value={start}
              onChange={(e) => setStart(Number(e.target.value))}
            />
          </label>

          <label style={{ display: "grid", gap: 6 }}>
            <span style={{ fontSize: 12, color: "#6b7280" }}>Entry size (SOL)</span>
            <input
              style={inputStyle}
              type="number"
              step="0.01"
              value={entry}
              onChange={(e) => setEntry(Number(e.target.value))}
            />
          </label>
        </div>

        <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12 }}>
          <input
            type="checkbox"
            checked={accurate}
            onChange={(e) => setAccurate(e.target.checked)}
          />
          <span style={{ fontSize: 13, color: "#374151" }}>
            Accurate mode (GeckoTerminal OHLCV candles — slower but precise)
          </span>
        </label>

        <div style={{ display: "flex", gap: 10, marginTop: 14, flexWrap: "wrap" }}>
          <button style={btnPrimary} onClick={run} disabled={loading}>
            {loading ? "Running..." : "Run simulation"}
          </button>

          <button
            style={btnSecondary}
            onClick={() => {
              setTpValues(DEFAULT_TP);
              setSlValues(DEFAULT_SL);
            }}
            disabled={loading}
          >
            Reset defaults
          </button>
        </div>

        {err && (
          <div style={{ marginTop: 10, color: "crimson", whiteSpace: "pre-wrap", fontSize: 13 }}>
            {err}
          </div>
        )}
      </div>

      {/* Results */}
      <section>
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Results</h2>

        {!data ? (
          <p style={{ color: "#9ca3af" }}>No results yet. Click "Run simulation".</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <p style={{ marginTop: 0, color: "#6b7280", fontSize: 13 }}>
              start: <b>{data.start_balance_sol}</b> SOL · entry: <b>{data.entry_sol}</b> SOL · combos:{" "}
              <b>{data.results.length}</b>
            </p>

            <div style={{ border: "1px solid #e5e7eb", borderRadius: 12 }}>
              <table cellPadding={0} style={{ borderCollapse: "collapse", width: "100%" }}>
                <thead style={{ background: "#f9fafb" }}>
                  <tr>
                    <th style={S.th}>#</th>
                    <th style={S.th}>TP%</th>
                    <th style={S.th}>SL%</th>
                    <th style={S.th}>Trades</th>
                    <th style={S.th}>TP hits</th>
                    <th style={S.th}>SL hits</th>
                    <th style={S.th}>TIME</th>
                    <th style={S.th}>Win rate (TP)</th>
                    <th style={S.th}>Avg PnL %</th>
                    <th style={S.th}>End balance (SOL)</th>
                  </tr>
                </thead>
                <tbody>
                  {data.results.map((r, i) => {
                    const isBest = i === 0;
                    const balanceColor = Number(r.end_balance_sol) >= data.start_balance_sol ? "#16a34a" : "#dc2626";
                    return (
                      <tr
                        key={`${r.tp_pct}-${r.sl_pct}-${i}`}
                        style={{ background: isBest ? "#f0fdf4" : "#fff" }}
                      >
                        <td style={{ ...S.td, color: "#9ca3af" }}>
                          {i + 1}
                          {isBest && (
                            <span style={{ marginLeft: 6, fontSize: 10, fontWeight: 700, color: "#16a34a", background: "#dcfce7", padding: "1px 5px", borderRadius: 4 }}>
                              ★ Best
                            </span>
                          )}
                        </td>
                        <td style={S.td}>{r.tp_pct}</td>
                        <td style={S.td}>{r.sl_pct}</td>
                        <td style={S.td}>{r.n_trades}</td>
                        <td style={{ ...S.td, color: "#16a34a", fontWeight: 600 }}>{r.tp}</td>
                        <td style={{ ...S.td, color: "#dc2626", fontWeight: 600 }}>{r.sl}</td>
                        <td style={S.td}>{r.time}</td>
                        <td style={S.td}>{Number(r.win_rate_tp_pct).toFixed(2)}%</td>
                        <td style={{ ...S.td, fontWeight: 600, color: Number(r.avg_pnl_pct) >= 0 ? "#16a34a" : "#dc2626" }}>
                          {Number(r.avg_pnl_pct) >= 0 ? "+" : ""}{Number(r.avg_pnl_pct).toFixed(2)}%
                        </td>
                        <td style={S.td}>
                          <b style={{ color: balanceColor }}>{Number(r.end_balance_sol).toFixed(2)}</b>
                        </td>
                      </tr>
                    );
                  })}

                  {data.results.length === 0 && (
                    <tr>
                      <td colSpan={10} style={{ padding: 20, color: "#9ca3af", textAlign: "center", fontSize: 13 }}>
                        No calls found for this channel.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </main>
  );
}
