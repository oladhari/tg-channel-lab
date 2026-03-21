// frontend/src/app/channels/[key]/page.tsx
import { getChannels, getCalls, getBestStats } from "../../../lib/api";
import { gmgnSolanaTokenUrl } from "../../../lib/links";
import { toJST } from "../../../lib/time";

export const dynamic = "force-dynamic";

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

function toNum(v: string | undefined, fallback: number) {
  if (!v) return fallback;
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

type SearchParams = { [k: string]: string | string[] | undefined };

export default async function ChannelPage(props: {
  params: any;
  searchParams?: any;
}) {
  const params = await Promise.resolve(props.params);
  const searchParams: SearchParams = await Promise.resolve(props.searchParams ?? {});

  const channelKeyRaw = params?.key;
  const channelKey = typeof channelKeyRaw === "string" ? channelKeyRaw : "";

  const start = toNum(typeof searchParams.start === "string" ? searchParams.start : undefined, 1.0);
  const entry = toNum(typeof searchParams.entry === "string" ? searchParams.entry : undefined, 0.1);

  const [channels, bestStatsAll, calls] = await Promise.all([
    getChannels(),
    getBestStats({ start_balance_sol: start, entry_sol: entry }),
    channelKey
      ? getCalls({ channel_key: channelKey, strategy_key: "tp35_sl20", limit: 200 })
      : getCalls({ strategy_key: "tp35_sl20", limit: 200 }),
  ]);

  const ch = channelKey ? channels.find((c) => c.key === channelKey) || null : null;

  const stat = bestStatsAll.find((s) => s.key === channelKey) ?? null;

  const telegramHref =
    ch?.telegram_username && ch.telegram_username.trim().length > 0
      ? `https://t.me/${ch.telegram_username.replace(/^@/, "")}`
      : null;

  return (
    <main style={S.page}>
      {/* Breadcrumb */}
      <div style={{ fontSize: 12, color: "#9ca3af", marginBottom: 12 }}>
        <a href="/" style={{ color: "#6b7280", textDecoration: "none" }}>Dashboard</a>
        <span style={{ margin: "0 6px" }}>/</span>
        <span style={{ color: "#374151" }}>{channelKey || "(missing key)"}</span>
      </div>

      {/* Page header */}
      <div style={{ marginBottom: 20, display: "flex", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
        <div style={{ flex: 1 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0, marginBottom: 6 }}>
            {channelKey || "(missing key!)"}
          </h1>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            {telegramHref ? (
              <a href={telegramHref} target="_blank" rel="noreferrer" style={{ fontSize: 13, color: "#1d4ed8", textDecoration: "none" }}>
                @{ch?.telegram_username.replace(/^@/, "")}
              </a>
            ) : (
              <span style={{ fontSize: 13, color: "#9ca3af" }}>(no telegram)</span>
            )}
            {ch && (
              <>
                <span style={S.pill(ch.enabled)}>{ch.enabled ? "Listening" : "Paused"}</span>
                <span style={S.pill(ch.live_enabled)}>{ch.live_enabled ? "Live" : "Paper"}</span>
              </>
            )}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
          <a
            href={`/channels/${channelKey}/simulation`}
            style={{ padding: "8px 14px", borderRadius: 8, background: "#f3f4f6", color: "#374151", border: "1px solid #e5e7eb", fontSize: 13, textDecoration: "none", fontWeight: 500 }}
          >
            Grid Simulation
          </a>
          <a
            href={`/channels/${channelKey}/settings`}
            style={{ padding: "8px 14px", borderRadius: 8, background: "#1d4ed8", color: "#fff", fontSize: 13, textDecoration: "none", fontWeight: 600 }}
          >
            ⚙ Live Settings
          </a>
        </div>
      </div>

      {/* Stat cards */}
      {stat ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 14, marginBottom: 28 }}>
          {/* Best Strategy */}
          <div style={S.card}>
            <div style={S.label}>Best Strategy</div>
            <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
              <span style={S.badge("#1d4ed8")}>TP {stat.best_tp_pct}%</span>
              <span style={S.badge("#7c3aed")}>SL {stat.best_sl_pct}%</span>
            </div>
          </div>

          {/* Total Trades */}
          <div style={S.cardDark}>
            <div style={S.label}>Total Trades</div>
            <div style={S.stat}>{stat.n_trades}</div>
          </div>

          {/* TP hits */}
          <div style={S.cardDark}>
            <div style={S.label}>TP hits</div>
            <div style={{ ...S.stat, color: "#16a34a" }}>{stat.tp}</div>
          </div>

          {/* SL hits */}
          <div style={S.cardDark}>
            <div style={S.label}>SL hits</div>
            <div style={{ ...S.stat, color: "#dc2626" }}>{stat.sl}</div>
          </div>

          {/* Win Rate */}
          <div style={S.cardDark}>
            <div style={S.label}>Win Rate</div>
            <div style={{ ...S.stat, color: Number(stat.win_rate_tp_pct) >= 50 ? "#16a34a" : "#dc2626" }}>
              {Number(stat.win_rate_tp_pct).toFixed(1)}%
            </div>
          </div>

          {/* Best Balance */}
          <div style={{ ...S.cardDark, borderColor: Number(stat.end_balance_sol) >= Number(stat.start_balance_sol) ? "#bbf7d0" : "#fecaca" }}>
            <div style={S.label}>Best Balance</div>
            <div style={{ ...S.stat, color: Number(stat.end_balance_sol) >= Number(stat.start_balance_sol) ? "#16a34a" : "#dc2626" }}>
              {Number(stat.end_balance_sol).toFixed(2)}
              <span style={{ fontSize: 14, fontWeight: 400, color: "#6b7280" }}> SOL</span>
            </div>
            <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 4 }}>
              from {Number(stat.start_balance_sol).toFixed(2)} SOL
            </div>
          </div>
        </div>
      ) : (
        <div style={{ ...S.cardDark, marginBottom: 28 }}>
          <p style={{ margin: 0, color: "#6b7280", fontSize: 13 }}>
            No completed calls yet — stats appear once recording finishes.
          </p>
        </div>
      )}

      {/* Calls table */}
      <section>
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
          Calls
          <span style={{ fontSize: 12, color: "#9ca3af", marginLeft: 10, fontWeight: 400 }}>latest 200</span>
        </h2>

        <div style={{ overflowX: "auto", border: "1px solid #e5e7eb", borderRadius: 12 }}>
          <table cellPadding={0} style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead style={{ background: "#f9fafb" }}>
              <tr>
                <th style={S.th}>ID</th>
                <th style={S.th}>Mint</th>
                <th style={S.th}>Status</th>
                <th style={S.th}>Entry Price</th>
                <th style={S.th}>Outcome</th>
                <th style={S.th}>PnL %</th>
                <th style={S.th}>Started JST</th>
              </tr>
            </thead>
            <tbody>
              {calls.map((c: any) => {
                const mint: string = typeof c.mint === "string" ? c.mint : "";
                const url = mint ? gmgnSolanaTokenUrl(mint) : null;
                const outcome: string = c.outcome ?? "";
                const outcomeColor = outcome === "TP" ? "#16a34a" : outcome === "SL" ? "#dc2626" : "#d97706";
                const pnl = c.pnl_pct != null ? Number(c.pnl_pct) : null;

                return (
                  <tr key={c.id} style={{ background: "#fff" }}>
                    <td style={S.td}>
                      <a href={`/calls/${c.id}`} style={{ color: "#1d4ed8", textDecoration: "none", fontWeight: 600 }}>
                        #{c.id}
                      </a>
                    </td>

                    <td style={{ ...S.td, fontFamily: "monospace" }}>
                      {url ? (
                        <a
                          href={url}
                          target="_blank"
                          rel="noreferrer"
                          style={{ textDecoration: "none", color: "#374151" }}
                          title="Open GMGN"
                        >
                          {mint.slice(0, 6)}…{mint.slice(-6)}
                        </a>
                      ) : (
                        <span style={{ color: "#9ca3af" }}>(no mint)</span>
                      )}
                    </td>

                    <td style={S.td}>
                      <span style={S.pill(c.status === "DONE")}>{c.status}</span>
                    </td>

                    <td style={{ ...S.td, fontFamily: "monospace", color: "#6b7280" }}>
                      {c.entry_price_usd != null ? Number(c.entry_price_usd).toFixed(8) : "—"}
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

                    <td style={{ ...S.td, color: "#9ca3af", fontSize: 12 }}>{toJST(c.started_at)}</td>
                  </tr>
                );
              })}

              {calls.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ padding: 20, color: "#9ca3af", textAlign: "center", fontSize: 13 }}>
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
