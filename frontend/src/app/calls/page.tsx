// frontend/src/app/calls/page.tsx
import { getCalls } from "../../lib/api";
import { gmgnSolanaTokenUrl } from "../../lib/links";

function shortMint(m: string) {
  return `${m.slice(0, 6)}…${m.slice(-6)}`;
}

export default async function CallsPage() {
  const rows = await getCalls({ limit: 200, strategy_key: "tp35_sl20" });

  return (
    <main style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <h1 style={{ marginBottom: 8 }}>Calls Explorer</h1>
      <p style={{ marginTop: 0, color: "#444" }}>
        Latest calls + tp35_sl20 outcome (observation only).
      </p>

      <div style={{ marginTop: 14 }}>
        <a href="/" style={{ textDecoration: "underline" }}>← Back to dashboard</a>
      </div>

      <section style={{ marginTop: 18 }}>
        <div style={{ overflowX: "auto" }}>
          <table cellPadding={10} style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>
                <th>Channel</th>
                <th>Mint</th>
                <th>Status</th>
                <th>Entry</th>
                <th>Outcome</th>
                <th>PnL %</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} style={{ borderBottom: "1px solid #f0f0f0" }}>
                  <td>{r.channel_key}</td>

                  <td style={{ fontFamily: "monospace" }}>
                    <a href={`/calls/${r.id}`} style={{ textDecoration: "underline", marginRight: 10 }}>
                      {shortMint(r.mint)}
                    </a>

                    <a
                      href={gmgnSolanaTokenUrl(r.mint)}
                      target="_blank"
                      rel="noreferrer"
                      style={{ textDecoration: "underline", color: "#444" }}
                      title="Open GMGN"
                    >
                      Dex
                    </a>

                    {r.symbol ? <span style={{ marginLeft: 8, color: "#666" }}>({r.symbol})</span> : null}
                  </td>

                  <td>{r.status}</td>
                  <td>{r.entry_price_usd == null ? "" : Number(r.entry_price_usd).toFixed(8)}</td>
                  <td>{r.outcome ?? ""}</td>
                  <td>{r.pnl_pct == null ? "" : `${Number(r.pnl_pct).toFixed(2)}%`}</td>
                  <td>{new Date(r.started_at).toLocaleString()}</td>
                </tr>
              ))}

              {rows.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ padding: 14, color: "#666" }}>
                    No calls yet.
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
