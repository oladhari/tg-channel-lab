// frontend/src/app/page.tsx
import AddChannelForm from "./AddChannelForm";
import ChannelRowActions from "./ChannelRowActions";
import { getChannels, getBestStats, getLiveConfig, getWallet } from "../lib/api";

function toNum(v: string | undefined, fallback: number) {
  if (!v) return fallback;
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

type SearchParams = { [key: string]: string | string[] | undefined };

export default async function Home(props: {
  searchParams?: any; // can be object OR Promise in some Next versions
}) {
  const searchParams: SearchParams = await Promise.resolve(props.searchParams ?? {});

  const start = toNum(typeof searchParams.start === "string" ? searchParams.start : undefined, 1.0);
  const entry = toNum(typeof searchParams.entry === "string" ? searchParams.entry : undefined, 0.1);

  const [channels, bestStats, liveCfg, wallet] = await Promise.all([
    getChannels(),
    getBestStats({ start_balance_sol: start, entry_sol: entry }),
    getLiveConfig(),
    getWallet().catch(() => null),
  ]);

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

  return (
    <main style={S.page}>

      {/* ── Page title row ── */}
      <div style={{ marginBottom: 20, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>Dashboard</h1>
          <p style={{ margin: 0, color: "#6b7280", fontSize: 13 }}>
            Live channels · paper stats · call explorer
          </p>
        </div>
      </div>

      {/* ── Top stat cards ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 14, marginBottom: 20 }}>

        {/* Wallet balance */}
        <div style={{ ...S.card }}>
          <div style={S.label}>Wallet balance</div>
          <div style={S.stat}>{wallet?.sol_balance != null ? `${wallet.sol_balance}` : "—"}<span style={{ fontSize: 14, fontWeight: 400, color: "#6b7280" }}> SOL</span></div>
          {wallet?.pubkey && (
            <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 4, fontFamily: "monospace" }}>
              {wallet.pubkey.slice(0, 8)}…{wallet.pubkey.slice(-8)}
            </div>
          )}
        </div>

        {/* Buys */}
        <div style={S.cardDark}>
          <div style={S.label}>Buys sent</div>
          <div style={S.stat}>{wallet?.total_buys ?? "—"}</div>
        </div>

        {/* Sells */}
        <div style={S.cardDark}>
          <div style={S.label}>Sells sent</div>
          <div style={S.stat}>{wallet?.total_sells ?? "—"}</div>
        </div>

        {/* Holding */}
        <div style={{ ...S.cardDark, borderColor: wallet?.holding ? "#fde68a" : undefined, background: wallet?.holding ? "#fffbeb" : undefined }}>
          <div style={S.label}>Currently holding</div>
          <div style={{ ...S.stat, color: wallet?.holding ? "#d97706" : undefined }}>{wallet?.holding ?? "—"}</div>
        </div>

        {/* GMGN status */}
        <div style={S.cardDark}>
          <div style={S.label}>GMGN fallback</div>
          <div style={{ marginTop: 6 }}>
            <span style={S.pill(!!liveCfg.gmgn_target_set)}>
              {liveCfg.gmgn_target_set ? "Configured" : "Not set"}
            </span>
          </div>
          <div style={{ fontSize: 11, color: "#9ca3af", marginTop: 4 }}>
            Strategy: <b>{liveCfg.live_strategy_key}</b>
          </div>
        </div>

      </div>

      {/* ── Live trading channels ── */}
      {wallet?.live_channels?.length ? (
        <div style={{ ...S.cardDark, marginBottom: 20 }}>
          <div style={{ ...S.label, marginBottom: 10 }}>Live trading channels</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
            {wallet.live_channels.map((ch) => (
              <a key={ch.id} href={`/channels/${ch.key}`} style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "6px 12px", borderRadius: 8,
                border: "1px solid #d1fae5", background: "#f0fdf4",
                textDecoration: "none", fontSize: 13,
              }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#22c55e", display: "inline-block", flexShrink: 0 }} />
                <b style={{ color: "#166534" }}>{ch.key}</b>
                <span style={{ color: "#6b7280" }}>@{ch.telegram_username}</span>
                {ch.live_buy_amount_sol != null && (
                  <span style={{ color: "#9ca3af", fontSize: 11 }}>{ch.live_buy_amount_sol} SOL</span>
                )}
              </a>
            ))}
          </div>
        </div>
      ) : null}

      {/* ── Add channel + channels table ── */}
      <AddChannelForm />

      <section style={{ marginTop: 28 }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Channels</h2>
        <div style={{ overflowX: "auto", border: "1px solid #e5e7eb", borderRadius: 12 }}>
          <table cellPadding={0} style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead style={{ background: "#f9fafb" }}>
              <tr>
                <th style={S.th}>ID</th>
                <th style={S.th}>Key</th>
                <th style={S.th}>Telegram</th>
                <th style={S.th}>Listening</th>
                <th style={S.th}>Live trading</th>
                <th style={{ ...S.th, borderBottom: "1px solid #e5e7eb" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {channels.map((c) => (
                <tr key={c.id} style={{ background: "#fff" }}>
                  <td style={{ ...S.td, color: "#9ca3af" }}>{c.id}</td>
                  <td style={S.td}>
                    <a href={`/channels/${c.key}`} style={{ color: "#1d4ed8", fontWeight: 600, textDecoration: "none" }}>
                      {c.key}
                    </a>
                  </td>
                  <td style={S.td}>
                    <a href={`https://t.me/${c.telegram_username}`} target="_blank" rel="noreferrer" style={{ color: "#6b7280" }}>
                      @{c.telegram_username}
                    </a>
                  </td>
                  <td style={S.td}><span style={S.pill(c.enabled)}>{c.enabled ? "On" : "Off"}</span></td>
                  <td style={S.td}><span style={S.pill(c.live_enabled)}>{c.live_enabled ? "Live" : "Paper"}</span></td>
                  <td style={S.td}>
                    <ChannelRowActions id={c.id} enabled={c.enabled} live_enabled={c.live_enabled} />
                  </td>
                </tr>
              ))}
              {channels.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ padding: 20, color: "#9ca3af", textAlign: "center", fontSize: 13 }}>
                    No channels yet — add one above.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* ── Best strategy per channel ── */}
      <section style={{ marginTop: 32 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
          <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>Best Strategy per Channel</h2>
          <span style={{ fontSize: 12, color: "#9ca3af" }}>
            grid: TP 20→100 × SL 10→50 (153 combos) · start {start} SOL · entry {entry} SOL
          </span>
          <span style={{ fontSize: 12, color: "#9ca3af" }}>
            cached 5 min · (change with <code style={{ background: "#f3f4f6", padding: "1px 5px", borderRadius: 4 }}>?start=1&entry=0.1</code>)
          </span>
        </div>
        <div style={{ overflowX: "auto", border: "1px solid #e5e7eb", borderRadius: 12 }}>
          <table cellPadding={0} style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead style={{ background: "#f9fafb" }}>
              <tr>
                <th style={S.th}>Channel</th>
                <th style={S.th}>Best Strategy</th>
                <th style={S.th}>Trades</th>
                <th style={S.th}>TP hits</th>
                <th style={S.th}>SL hits</th>
                <th style={S.th}>Win rate</th>
                <th style={S.th}>Avg PnL</th>
                <th style={S.th}>Best Balance</th>
              </tr>
            </thead>
            <tbody>
              {bestStats.map((s) => {
                const gain = Number(s.end_balance_sol) - Number(s.start_balance_sol);
                return (
                  <tr key={s.channel_id} style={{ background: "#fff" }}>
                    <td style={S.td}>
                      <a href={`/channels/${s.key}`} style={{ color: "#1d4ed8", fontWeight: 600, textDecoration: "none" }}>
                        {s.key}
                      </a>{" "}
                      <span style={{ color: "#9ca3af", fontSize: 11 }}>@{s.telegram_username}</span>
                    </td>
                    <td style={S.td}>
                      <span style={S.badge("#1d4ed8")}>TP {s.best_tp_pct}%</span>
                      {" "}
                      <span style={S.badge("#7c3aed")}>SL {s.best_sl_pct}%</span>
                    </td>
                    <td style={S.td}>{s.n_trades}</td>
                    <td style={{ ...S.td, color: "#16a34a", fontWeight: 600 }}>{s.tp}</td>
                    <td style={{ ...S.td, color: "#dc2626", fontWeight: 600 }}>{s.sl}</td>
                    <td style={S.td}>
                      <span style={S.badge(Number(s.win_rate_tp_pct) >= 50 ? "#16a34a" : "#dc2626")}>
                        {Number(s.win_rate_tp_pct).toFixed(1)}%
                      </span>
                    </td>
                    <td style={{ ...S.td, fontWeight: 600, color: Number(s.avg_pnl_pct) >= 0 ? "#16a34a" : "#dc2626" }}>
                      {Number(s.avg_pnl_pct) >= 0 ? "+" : ""}{Number(s.avg_pnl_pct).toFixed(2)}%
                    </td>
                    <td style={S.td}>
                      <span style={{ color: "#6b7280" }}>{Number(s.start_balance_sol).toFixed(2)}</span>
                      {" → "}
                      <b style={{ color: gain >= 0 ? "#16a34a" : "#dc2626" }}>
                        {Number(s.end_balance_sol).toFixed(2)} SOL
                      </b>
                    </td>
                  </tr>
                );
              })}
              {bestStats.length === 0 && (
                <tr>
                  <td colSpan={8} style={{ padding: 20, color: "#9ca3af", textAlign: "center", fontSize: 13 }}>
                    No completed calls yet — stats appear once recording finishes.
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
