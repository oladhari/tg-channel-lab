// frontend/src/app/channels/[key]/page.tsx
import PaperControls from "../../PaperControls";
import { getChannels, getCalls, getPaperStats } from "../../../lib/api";

function toNum(v: string | undefined, fallback: number) {
  if (!v) return fallback;
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function makeStrategyKey(tp: number, sl: number) {
  return `tp${tp}_sl${sl}`;
}

export default async function ChannelPage({
  params,
  searchParams,
}: {
  params: { key: string };
  searchParams?: { [k: string]: string | string[] | undefined };
}) {
  const channelKey = params.key;

  const tp = toNum(typeof searchParams?.tp === "string" ? searchParams.tp : undefined, 35);
  const sl = toNum(typeof searchParams?.sl === "string" ? searchParams.sl : undefined, 20);
  const start = toNum(typeof searchParams?.start === "string" ? searchParams.start : undefined, 1.0);
  const entry = toNum(typeof searchParams?.entry === "string" ? searchParams.entry : undefined, 0.1);

  const strategy_key = makeStrategyKey(tp, sl);

  const [channels, statsArr, calls] = await Promise.all([
    getChannels(),
    getPaperStats({ strategy_key, start_balance_sol: start, entry_sol: entry, channel_key: channelKey }),
    getCalls({ channel_key: channelKey, strategy_key, limit: 200, offset: 0 }),
  ]);

  const ch = channels.find((c) => c.key === channelKey) || null;
  const stat = statsArr[0] || null;

  return (
    <main style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <p style={{ marginTop: 0 }}>
        <a href="/" style={{ textDecoration: "underline" }}>← Back to dashboard</a>{" "}
        <span style={{ margin: "0 8px", color: "#bbb" }}>|</span>
        <a href="/calls" style={{ textDecoration: "underline" }}>Open Calls Explorer</a>
      </p>

      <h1 style={{ marginBottom: 8 }}>Channel: {channelKey}</h1>

      {ch ? (
        <p style={{ marginTop: 0, color: "#444" }}>
          Telegram:{" "}
          <a
            href={`https://t.me/${ch.telegram_username}`}
            target="_blank"
            rel="noreferrer"
            style={{ textDecoration: "underline" }}
          >
            @{ch.telegram_username}
          </a>{" "}
          • enabled: {ch.enabled ? "✅" : "❌"} • live: {ch.live_enabled ? "✅" : "❌"}
        </p>
      ) : (
        <p style={{ marginTop: 0, color: "#444" }}>Telegram: (unknown)</p>
      )}

      <PaperControls />

      <section style={{ marginTop: 24 }}>
        <h2 style={{ marginBottom: 10 }}>
          Paper Stats ({strategy_key}) — start {start} SOL, entry {entry} SOL
        </h2>

        {!stat ? (
          <p style={{ color: "#666" }}>No stats yet for this channel/strategy.</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table cellPadding={10} style={{ borderCollapse: "collapse", width: "100%" }}>
              <thead>
                <tr style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>
                  <th>Trades</th>
                  <th>TP</th>
                  <th>SL</th>
                  <th>TIME</th>
                  <th>Win rate (TP)</th>
                  <th>Avg PnL %</th>
                  <th>Balance (start → end)</th>
                </tr>
              </thead>
              <tbody>
                <tr style={{ borderBottom: "1px solid #f0f0f0" }}>
                  <td>{stat.n_trades}</td>
                  <td>{stat.tp}</td>
                  <td>{stat.sl}</td>
                  <td>{stat.time}</td>
                  <td>{Number(stat.win_rate_tp_pct).toFixed(2)}%</td>
                  <td>{Number(stat.avg_pnl_pct).toFixed(2)}%</td>
                  <td>
                    {Number(stat.start_balance_sol).toFixed(2)} →{" "}
                    <b>{Number(stat.end_balance_sol).toFixed(2)}</b>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section style={{ marginTop: 24 }}>
        <h2 style={{ marginBottom: 10 }}>Calls (latest 200)</h2>
        <div style={{ overflowX: "auto" }}>
          <table cellPadding={10} style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>
                <th>ID</th>
                <th>Mint</th>
                <th>Status</th>
                <th>Outcome</th>
                <th>PnL %</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {calls.map((c) => (
                <tr key={c.id} style={{ borderBottom: "1px solid #f0f0f0" }}>
                  <td>
                    <a href={`/calls/${c.id}`} style={{ textDecoration: "underline" }}>
                      {c.id}
                    </a>
                  </td>
                  <td style={{ fontFamily: "monospace" }}>
                    {c.mint.slice(0, 6)}…{c.mint.slice(-6)}
                  </td>
                  <td>{c.status}</td>
                  <td>{c.outcome ?? ""}</td>
                  <td>{c.pnl_pct != null ? `${Number(c.pnl_pct).toFixed(2)}%` : ""}</td>
                  <td>{new Date(c.started_at).toLocaleString()}</td>
                </tr>
              ))}

              {calls.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ padding: 14, color: "#666" }}>
                    No calls for this channel yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
