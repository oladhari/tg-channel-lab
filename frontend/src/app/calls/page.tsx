// frontend/src/app/calls/page.tsx
import { getCalls } from "../../lib/api";
import { gmgnSolanaTokenUrl } from "../../lib/links";
import { toJST } from "../../lib/time";

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

function shortMint(m: string) {
  return `${m.slice(0, 6)}…${m.slice(-6)}`;
}

export default async function CallsPage() {
  const rows = await getCalls({ limit: 200, strategy_key: "tp35_sl20" });

  return (
    <main style={S.page}>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: "0 0 4px" }}>Calls Explorer</h1>
        <p style={{ margin: 0, color: "#6b7280", fontSize: 13 }}>
          Latest 200 calls · outcomes from recorded tp35/sl20 strategy
        </p>
      </div>

      <div style={{ overflowX: "auto", border: "1px solid #e5e7eb", borderRadius: 12 }}>
        <table cellPadding={0} style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead style={{ background: "#f9fafb" }}>
            <tr>
              <th style={S.th}>Channel</th>
              <th style={S.th}>Mint</th>
              <th style={S.th}>Status</th>
              <th style={S.th}>Entry</th>
              <th style={S.th}>Outcome</th>
              <th style={S.th}>PnL %</th>
              <th style={S.th}>Started JST</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const outcome: string = r.outcome ?? "";
              const outcomeColor = outcome === "TP" ? "#16a34a" : outcome === "SL" ? "#dc2626" : "#d97706";
              const pnl = r.pnl_pct != null ? Number(r.pnl_pct) : null;

              return (
                <tr key={r.id} style={{ background: "#fff" }}>
                  <td style={S.td}>
                    <a href={`/channels/${r.channel_key}`} style={{ color: "#1d4ed8", fontWeight: 600, textDecoration: "none" }}>
                      {r.channel_key}
                    </a>
                  </td>

                  <td style={{ ...S.td, fontFamily: "monospace" }}>
                    <a href={`/calls/${r.id}`} style={{ color: "#374151", textDecoration: "none", marginRight: 8 }}>
                      {shortMint(r.mint)}
                    </a>
                    <a
                      href={gmgnSolanaTokenUrl(r.mint)}
                      target="_blank"
                      rel="noreferrer"
                      style={{ color: "#9ca3af", fontSize: 11, textDecoration: "none" }}
                      title="Open GMGN"
                    >
                      GMGN
                    </a>
                    {r.symbol ? <span style={{ marginLeft: 6, color: "#9ca3af", fontSize: 11 }}>({r.symbol})</span> : null}
                  </td>

                  <td style={S.td}>
                    <span style={S.pill(r.status === "DONE")}>{r.status}</span>
                  </td>

                  <td style={{ ...S.td, fontFamily: "monospace", color: "#6b7280" }}>
                    {r.entry_price_usd == null ? "—" : Number(r.entry_price_usd).toFixed(8)}
                  </td>

                  <td style={S.td}>
                    {outcome ? (
                      <span style={S.badge(outcomeColor)}>{outcome}</span>
                    ) : (
                      <span style={{ color: "#9ca3af" }}>—</span>
                    )}
                  </td>

                  <td style={{ ...S.td, fontWeight: 600, color: pnl == null ? undefined : pnl >= 0 ? "#16a34a" : "#dc2626" }}>
                    {pnl != null ? `${pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}%` : "—"}
                  </td>

                  <td style={{ ...S.td, color: "#9ca3af", fontSize: 12 }}>{toJST(r.started_at)}</td>
                </tr>
              );
            })}

            {rows.length === 0 && (
              <tr>
                <td colSpan={7} style={{ padding: 20, color: "#9ca3af", textAlign: "center", fontSize: 13 }}>
                  No calls yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}
