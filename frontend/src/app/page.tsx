import { getChannels, getPaperStats } from "../lib/api";

export default async function Home() {
  const [channels, stats] = await Promise.all([getChannels(), getPaperStats()]);

  return (
    <main style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <h1 style={{ marginBottom: 8 }}>TG Channel Lab</h1>
      <p style={{ marginTop: 0, color: "#444" }}>
        Recording calls + tracking price points + paper stats (no filters).
      </p>
      <p style={{ marginTop: 10 }}>
        <a href="/calls" style={{ textDecoration: "underline" }}>
          Open Calls Explorer →
        </a>
      </p>


      <section style={{ marginTop: 28 }}>
        <h2 style={{ marginBottom: 10 }}>Channels</h2>
        <div style={{ overflowX: "auto" }}>
          <table cellPadding={10} style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>
                <th>ID</th>
                <th>Key</th>
                <th>Telegram</th>
                <th>Enabled</th>
                <th>Live</th>
              </tr>
            </thead>
            <tbody>
              {channels.map((c) => (
                <tr key={c.id} style={{ borderBottom: "1px solid #f0f0f0" }}>
                  <td>{c.id}</td>
                  <td>{c.key}</td>
                  <td>
                    <a
                      href={`https://t.me/${c.telegram_username}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      @{c.telegram_username}
                    </a>
                  </td>
                  <td>{c.enabled ? "✅" : "❌"}</td>
                  <td>{c.live_enabled ? "✅" : "❌"}</td>
                </tr>
              ))}
              {channels.length === 0 && (
                <tr>
                  <td colSpan={5} style={{ padding: 14, color: "#666" }}>
                    No channels yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section style={{ marginTop: 28 }}>
        <h2 style={{ marginBottom: 10 }}>Paper Stats (tp35_sl20)</h2>
        <div style={{ overflowX: "auto" }}>
          <table cellPadding={10} style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>
                <th>Channel</th>
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
              {stats.map((s) => (
                <tr key={`${s.channel_id}-${s.strategy_key}`} style={{ borderBottom: "1px solid #f0f0f0" }}>
                  <td>
                    <b>{s.key}</b> <span style={{ color: "#666" }}>@{s.telegram_username}</span>
                  </td>
                  <td>{s.n_trades}</td>
                  <td>{s.tp}</td>
                  <td>{s.sl}</td>
                  <td>{s.time}</td>
                  <td>{Number(s.win_rate_tp_pct).toFixed(2)}%</td>
                  <td>{Number(s.avg_pnl_pct).toFixed(2)}%</td>
                  <td>
                    {Number(s.start_balance_sol).toFixed(2)} →{" "}
                    <b>{Number(s.end_balance_sol).toFixed(2)}</b>
                  </td>
                </tr>
              ))}
              {stats.length === 0 && (
                <tr>
                  <td colSpan={8} style={{ padding: 14, color: "#666" }}>
                    No stats yet.
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
