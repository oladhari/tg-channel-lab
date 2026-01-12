// frontend/src/app/channels/[key]/simulation/page.tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { getGridSim, type GridSim } from "../../../../lib/api";

const DEFAULT_TP = "35,40,45,50,55,60,65";
const DEFAULT_SL = "20,25,30,35,40,45,50";

export default function ChannelSimulationPage(props: { params: { key: string } }) {
  const channelKey = props.params?.key ?? "";

  const [tpValues, setTpValues] = useState(DEFAULT_TP);
  const [slValues, setSlValues] = useState(DEFAULT_SL);
  const [start, setStart] = useState(1.0);
  const [entry, setEntry] = useState(0.1);

  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [data, setData] = useState<GridSim | null>(null);

  async function run() {
    setLoading(true);
    setErr(null);
    try {
      const res = await getGridSim({
        channel_key: channelKey,
        tp_values: tpValues,
        sl_values: slValues,
        start_balance_sol: start,
        entry_sol: entry,
      });
      setData(res);
    } catch (e: any) {
      setErr(e?.message || String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <p style={{ marginTop: 0 }}>
        <a href={`/channels/${channelKey}`} style={{ textDecoration: "underline" }}>
          ← Back to channel
        </a>
      </p>

      <h1 style={{ marginBottom: 6 }}>Simulation: {channelKey}</h1>
      <p style={{ marginTop: 0, color: "#555" }}>
        Run a TP/SL grid on stored <code>price_points</code>. No Telegram involved.
      </p>

      <div style={{ border: "1px solid #ddd", borderRadius: 10, padding: 14, marginTop: 16 }}>
        <h3 style={{ marginTop: 0, marginBottom: 12 }}>Controls</h3>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(240px, 1fr))", gap: 12 }}>
          <label style={{ display: "grid", gap: 6 }}>
            <span style={{ fontSize: 12, color: "#555" }}>TP values (CSV)</span>
            <input value={tpValues} onChange={(e) => setTpValues(e.target.value)} />
          </label>

          <label style={{ display: "grid", gap: 6 }}>
            <span style={{ fontSize: 12, color: "#555" }}>SL values (CSV)</span>
            <input value={slValues} onChange={(e) => setSlValues(e.target.value)} />
          </label>

          <label style={{ display: "grid", gap: 6 }}>
            <span style={{ fontSize: 12, color: "#555" }}>Start balance (SOL)</span>
            <input type="number" step="0.01" value={start} onChange={(e) => setStart(Number(e.target.value))} />
          </label>

          <label style={{ display: "grid", gap: 6 }}>
            <span style={{ fontSize: 12, color: "#555" }}>Entry size (SOL)</span>
            <input type="number" step="0.01" value={entry} onChange={(e) => setEntry(Number(e.target.value))} />
          </label>
        </div>

        <div style={{ display: "flex", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
          <button onClick={run} disabled={loading || !channelKey}>
            {loading ? "Running..." : "Run simulation"}
          </button>

          <button
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
          <div style={{ marginTop: 10, color: "crimson", whiteSpace: "pre-wrap" }}>
            {err}
          </div>
        )}
      </div>

      <section style={{ marginTop: 22 }}>
        <h2 style={{ marginBottom: 10 }}>Results</h2>

        {!data ? (
          <p style={{ color: "#666" }}>No results yet. Click “Run simulation”.</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <p style={{ marginTop: 0, color: "#555" }}>
              start: <b>{data.start_balance_sol}</b> SOL • entry: <b>{data.entry_sol}</b> SOL • combos:{" "}
              <b>{data.results.length}</b>
            </p>

            <table cellPadding={10} style={{ borderCollapse: "collapse", width: "100%" }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>
                  <th>TP%</th>
                  <th>SL%</th>
                  <th>Trades</th>
                  <th>TP</th>
                  <th>SL</th>
                  <th>TIME</th>
                  <th>Win rate (TP)</th>
                  <th>Avg PnL %</th>
                  <th>End balance (SOL)</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((r, i) => (
                  <tr key={`${r.tp_pct}-${r.sl_pct}-${i}`} style={{ borderBottom: "1px solid #f0f0f0" }}>
                    <td>{r.tp_pct}</td>
                    <td>{r.sl_pct}</td>
                    <td>{r.n_trades}</td>
                    <td>{r.tp}</td>
                    <td>{r.sl}</td>
                    <td>{r.time}</td>
                    <td>{Number(r.win_rate_tp_pct).toFixed(2)}%</td>
                    <td>{Number(r.avg_pnl_pct).toFixed(2)}%</td>
                    <td>
                      <b>{Number(r.end_balance_sol).toFixed(2)}</b>
                    </td>
                  </tr>
                ))}

                {data.results.length === 0 && (
                  <tr>
                    <td colSpan={9} style={{ padding: 14, color: "#666" }}>
                      No calls found for this channel.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
