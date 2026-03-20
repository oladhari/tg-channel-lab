// frontend/src/app/page.tsx
import AddChannelForm from "./AddChannelForm";
import ChannelRowActions from "./ChannelRowActions";
import { getChannels, getPaperStats, getLiveConfig, getWallet } from "../lib/api";

function toNum(v: string | undefined, fallback: number) {
  if (!v) return fallback;
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function makeStrategyKey(tp: number, sl: number) {
  return `tp${tp}_sl${sl}`;
}

type SearchParams = { [key: string]: string | string[] | undefined };

export default async function Home(props: {
  searchParams?: any; // can be object OR Promise in some Next versions
}) {
  const searchParams: SearchParams = await Promise.resolve(props.searchParams ?? {});

  const tp = toNum(typeof searchParams.tp === "string" ? searchParams.tp : undefined, 35);
  const sl = toNum(typeof searchParams.sl === "string" ? searchParams.sl : undefined, 20);
  const start = toNum(typeof searchParams.start === "string" ? searchParams.start : undefined, 1.0);
  const entry = toNum(typeof searchParams.entry === "string" ? searchParams.entry : undefined, 0.1);

  const strategy_key = makeStrategyKey(tp, sl);

  const [channels, stats, liveCfg, wallet] = await Promise.all([
    getChannels(),
    getPaperStats({ strategy_key, start_balance_sol: start, entry_sol: entry }),
    getLiveConfig(),
    getWallet().catch(() => null),
  ]);

  return (
    <main style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <h1 style={{ marginBottom: 8 }}>TG Channel Lab</h1>
      <p style={{ marginTop: 0, color: "#444" }}>
        Recording calls + tracking price points + paper stats (no filters).
      </p>

      {/* ── Wallet panel ── */}
      <div style={{ marginTop: 16, padding: 16, background: "#f8faff", border: "1px solid #c8d8f0", borderRadius: 12 }}>
        <div style={{ display: "flex", gap: 32, flexWrap: "wrap", alignItems: "flex-start" }}>

          {/* Balance + pubkey */}
          <div>
            <div style={{ fontSize: 12, color: "#888", marginBottom: 2 }}>Wallet balance</div>
            <div style={{ fontSize: 28, fontWeight: 700, letterSpacing: "-0.5px" }}>
              {wallet?.sol_balance != null ? `${wallet.sol_balance} SOL` : "—"}
            </div>
            {wallet?.pubkey && (
              <div style={{ fontSize: 11, color: "#888", marginTop: 2, fontFamily: "monospace" }}>
                {wallet.pubkey.slice(0, 8)}…{wallet.pubkey.slice(-8)}
              </div>
            )}
          </div>

          {/* Trade counters */}
          <div style={{ display: "flex", gap: 24 }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 22, fontWeight: 700 }}>{wallet?.total_buys ?? "—"}</div>
              <div style={{ fontSize: 11, color: "#666" }}>Buys sent</div>
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 22, fontWeight: 700 }}>{wallet?.total_sells ?? "—"}</div>
              <div style={{ fontSize: 11, color: "#666" }}>Sells sent</div>
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 22, fontWeight: 700, color: wallet?.holding ? "#d97706" : undefined }}>
                {wallet?.holding ?? "—"}
              </div>
              <div style={{ fontSize: 11, color: "#666" }}>Holding</div>
            </div>
          </div>

          {/* Live channels */}
          <div>
            <div style={{ fontSize: 12, color: "#888", marginBottom: 6 }}>Live trading channels</div>
            {wallet?.live_channels?.length ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {wallet.live_channels.map((ch) => (
                  <div key={ch.id} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#22c55e", display: "inline-block" }} />
                    <a href={`/channels/${ch.key}`} style={{ textDecoration: "underline", fontWeight: 600 }}>
                      {ch.key}
                    </a>
                    <span style={{ color: "#666", fontSize: 12 }}>@{ch.telegram_username}</span>
                    <span style={{ color: "#888", fontSize: 12 }}>
                      {ch.live_buy_amount_sol != null ? `${ch.live_buy_amount_sol} SOL/trade` : ""}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ color: "#999", fontSize: 13 }}>No channels live trading</div>
            )}
          </div>

        </div>
      </div>

      <div style={{ marginTop: 10, padding: 12, border: "1px solid #eee", borderRadius: 12 }}>
        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "center" }}>
          <b>Live sell (GMGN)</b>
          <span style={{ color: liveCfg.gmgn_target_set ? "#0b5" : "crimson" }}>
            {liveCfg.gmgn_target_set ? "GMGN_TARGET set ✅" : "GMGN_TARGET missing ❌"}
          </span>
          <span style={{ color: "#666" }}>Sell: {liveCfg.gmgn_sell_percent}</span>
          <span style={{ color: "#666" }}>Strategy: {liveCfg.live_strategy_key}</span>
          <a href="/calls" style={{ textDecoration: "underline", marginLeft: "auto" }}>
            Open Calls Explorer →
          </a>
        </div>
      </div>

      <p style={{ marginTop: 10 }}>
        <a href="/live" style={{ textDecoration: "underline" }}>
          Open Live Queue →
        </a>
      </p>

      <AddChannelForm />

      {/* rest unchanged */}
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
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {channels.map((c) => (
                <tr key={c.id} style={{ borderBottom: "1px solid #f0f0f0" }}>
                  <td>{c.id}</td>
                  <td>
                    <a href={`/channels/${c.key}`} style={{ textDecoration: "underline" }}>
                      {c.key}
                    </a>
                  </td>
                  <td>
                    <a href={`https://t.me/${c.telegram_username}`} target="_blank" rel="noreferrer">
                      @{c.telegram_username}
                    </a>
                  </td>
                  <td>{c.enabled ? "✅" : "❌"}</td>
                  <td>{c.live_enabled ? "✅" : "❌"}</td>
                  <td>
                    <ChannelRowActions id={c.id} enabled={c.enabled} live_enabled={c.live_enabled} />
                  </td>
                </tr>
              ))}

              {channels.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ padding: 14, color: "#666" }}>
                    No channels yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section style={{ marginTop: 28 }}>
        <h2 style={{ marginBottom: 10 }}>
          Paper Stats ({strategy_key}) — start {start} SOL, entry {entry} SOL
        </h2>
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
                    <a href={`/channels/${s.key}`} style={{ textDecoration: "underline" }}>
                      <b>{s.key}</b>
                    </a>{" "}
                    <span style={{ color: "#666" }}>@{s.telegram_username}</span>
                  </td>
                  <td>{s.n_trades}</td>
                  <td>{s.tp}</td>
                  <td>{s.sl}</td>
                  <td>{s.time}</td>
                  <td>{Number(s.win_rate_tp_pct).toFixed(2)}%</td>
                  <td>{Number(s.avg_pnl_pct).toFixed(2)}%</td>
                  <td>
                    {Number(s.start_balance_sol).toFixed(2)} → <b>{Number(s.end_balance_sol).toFixed(2)}</b>
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
