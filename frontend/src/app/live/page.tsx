// frontend/src/app/live/page.tsx
import { getLiveQueue } from "../../lib/api";

export default async function LivePage() {
  const rows = await getLiveQueue();

  return (
    <main style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <h1 style={{ marginBottom: 8 }}>Live Queue</h1>
      <p style={{ marginTop: 0, color: "#444" }}>
        Calls with live selling enabled (GMGN).
      </p>

      <div style={{ overflowX: "auto", marginTop: 14 }}>
        <table cellPadding={10} style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>
              <th>Call ID</th>
              <th>Channel</th>
              <th>Mint</th>
              <th>Status</th>
              <th>Sell Status</th>
              <th>Reason</th>
              <th>Error</th>
              <th>Started</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r: any) => (
              <tr key={r.id} style={{ borderBottom: "1px solid #f0f0f0" }}>
                <td>{r.id}</td>
                <td>
                  <b>{r.channel_key}</b> <span style={{ color: "#666" }}>@{r.telegram_username}</span>
                </td>
                <td style={{ fontFamily: "monospace" }}>{r.mint?.slice(0, 10)}...</td>
                <td>{r.status}</td>
                <td>{r.live_sell_status}</td>
                <td>{r.live_sell_reason || r.outcome || ""}</td>
                <td style={{ color: r.live_sell_error ? "crimson" : "#666" }}>
                  {r.live_sell_error ? String(r.live_sell_error).slice(0, 60) : ""}
                </td>
                <td>{String(r.started_at).slice(0, 19)}</td>
              </tr>
            ))}

            {rows.length === 0 && (
              <tr>
                <td colSpan={8} style={{ padding: 14, color: "#666" }}>
                  Empty.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}
