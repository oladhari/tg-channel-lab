// frontend/src/app/calls/[id]/page.tsx
import { getCall, getCallPrices } from "../../../lib/api";
import PriceChart from "./PriceChart";
import { gmgnSolanaTokenUrl } from "../../../lib/links";
import { toJST } from "../../../lib/time";

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

type Props = {
  params: any;
};

export default async function CallDetailPage(props: Props) {
  const params = await Promise.resolve(props.params);
  const idRaw = params?.id;
  const id = Number(typeof idRaw === "string" ? idRaw : "");

  if (!Number.isFinite(id) || id <= 0) {
    return (
      <main style={S.page}>
        <div style={{ fontSize: 12, color: "#9ca3af", marginBottom: 12 }}>
          <a href="/calls" style={{ color: "#6b7280", textDecoration: "none" }}>Calls Explorer</a>
          <span style={{ margin: "0 6px" }}>/</span>
          <span style={{ color: "#374151" }}>Invalid ID</span>
        </div>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: "0 0 8px" }}>Invalid Call ID</h1>
        <p style={{ color: "#6b7280" }}>
          Got: <code>{String(idRaw)}</code>
        </p>
      </main>
    );
  }

  const [call, prices] = await Promise.all([getCall(id), getCallPrices(id)]);

  // Use first strategy result instead of hardcoding tp35_sl20
  const sr = call.strategy_results[0] ?? null;

  const entryPrice = sr?.entry_price_usd ?? call.entry_price_usd ?? null;
  const exitT = sr?.exit_t_sec ?? null;
  const exitPrice = sr?.exit_price_usd ?? null;

  const tpPrice = sr && entryPrice != null ? entryPrice * (1 + sr.tp_pct / 100) : null;
  const slPrice = sr && entryPrice != null ? entryPrice * (1 - sr.sl_pct / 100) : null;

  return (
    <main style={S.page}>
      {/* Breadcrumb */}
      <div style={{ fontSize: 12, color: "#9ca3af", marginBottom: 12 }}>
        <a href="/calls" style={{ color: "#6b7280", textDecoration: "none" }}>Calls Explorer</a>
        <span style={{ margin: "0 6px" }}>/</span>
        <span style={{ color: "#374151" }}>Call #{call.id}</span>
      </div>

      {/* Page header */}
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: "0 0 10px" }}>Call #{call.id}</h1>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center", fontSize: 13, color: "#6b7280" }}>
          <span>
            Channel:{" "}
            <a href={`/channels/${call.channel_key}`} style={{ color: "#1d4ed8", fontWeight: 600, textDecoration: "none" }}>
              {call.channel_key}
            </a>
          </span>
          <span>
            Mint:{" "}
            <a
              href={gmgnSolanaTokenUrl(call.mint)}
              target="_blank"
              rel="noreferrer"
              style={{ fontFamily: "monospace", color: "#374151", textDecoration: "none" }}
              title="Open GMGN"
            >
              {call.mint.slice(0, 8)}…{call.mint.slice(-8)}
            </a>
          </span>
          <span style={S.pill(call.status === "DONE")}>{call.status}</span>
          <span style={{ color: "#9ca3af" }}>Started: {toJST(call.started_at)}</span>
          <a
            href={gmgnSolanaTokenUrl(call.mint)}
            target="_blank"
            rel="noreferrer"
            style={{ color: "#1d4ed8", textDecoration: "none", fontSize: 12 }}
          >
            Open GMGN →
          </a>
        </div>
      </div>

      {/* Price chart */}
      <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 10 }}>Price</h2>
      <PriceChart
        prices={prices ?? []}
        entryPrice={entryPrice}
        tpPrice={tpPrice}
        slPrice={slPrice}
        exitT={exitT}
        exitPrice={exitPrice}
      />

      {/* Strategy results table */}
      <h2 style={{ fontSize: 16, fontWeight: 600, margin: "24px 0 12px" }}>Strategy Results</h2>
      <div style={{ overflowX: "auto", border: "1px solid #e5e7eb", borderRadius: 12 }}>
        <table cellPadding={0} style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead style={{ background: "#f9fafb" }}>
            <tr>
              <th style={S.th}>Strategy Key</th>
              <th style={S.th}>Outcome</th>
              <th style={S.th}>PnL %</th>
              <th style={S.th}>Exit T (sec)</th>
              <th style={S.th}>Exit Price (USD)</th>
            </tr>
          </thead>
          <tbody>
            {call.strategy_results.map((r) => {
              const outcome: string = r.outcome ?? "";
              const outcomeColor = outcome === "TP" ? "#16a34a" : outcome === "SL" ? "#dc2626" : "#d97706";
              const pnl = Number(r.pnl_pct);
              return (
                <tr key={r.strategy_key} style={{ background: "#fff" }}>
                  <td style={{ ...S.td, fontFamily: "monospace", fontSize: 12 }}>{r.strategy_key}</td>
                  <td style={S.td}>
                    {outcome ? (
                      <span style={S.badge(outcomeColor)}>{outcome}</span>
                    ) : (
                      <span style={{ color: "#9ca3af" }}>—</span>
                    )}
                  </td>
                  <td style={{ ...S.td, fontWeight: 600, color: pnl >= 0 ? "#16a34a" : "#dc2626" }}>
                    {pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}%
                  </td>
                  <td style={{ ...S.td, color: "#6b7280" }}>{r.exit_t_sec ?? "—"}</td>
                  <td style={{ ...S.td, fontFamily: "monospace", color: "#6b7280" }}>
                    {r.exit_price_usd != null ? Number(r.exit_price_usd).toFixed(8) : "—"}
                  </td>
                </tr>
              );
            })}

            {call.strategy_results.length === 0 && (
              <tr>
                <td colSpan={5} style={{ padding: 20, color: "#9ca3af", textAlign: "center", fontSize: 13 }}>
                  No strategy results yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </main>
  );
}
