// frontend/src/app/channels/[key]/page.tsx
import { getChannels, getCalls, getPaperStats } from "../../../lib/api";

export const dynamic = "force-dynamic";

function toNum(v: string | undefined, fallback: number) {
  if (!v) return fallback;
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function makeStrategyKey(tp: number, sl: number) {
  return `tp${tp}_sl${sl}`;
}

function dexscreenerSolanaUrl(mint: string) {
  return `https://dexscreener.com/solana/${mint}`;
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

  const tp = toNum(typeof searchParams.tp === "string" ? searchParams.tp : undefined, 35);
  const sl = toNum(typeof searchParams.sl === "string" ? searchParams.sl : undefined, 20);
  const start = toNum(typeof searchParams.start === "string" ? searchParams.start : undefined, 1.0);
  const entry = toNum(typeof searchParams.entry === "string" ? searchParams.entry : undefined, 0.1);

  const strategy_key = makeStrategyKey(tp, sl);

  const [channels, statsArr, calls] = await Promise.all([
    getChannels(),
    channelKey
      ? getPaperStats({ strategy_key, start_balance_sol: start, entry_sol: entry, channel_key: channelKey })
      : getPaperStats({ strategy_key, start_balance_sol: start, entry_sol: entry }),
    channelKey
      ? getCalls({ channel_key: channelKey, strategy_key, limit: 200, offset: 0 })
      : getCalls({ strategy_key, limit: 200, offset: 0 }),
  ]);

  const ch = channelKey ? channels.find((c) => c.key === channelKey) || null : null;

  const stat =
    channelKey
      ? (statsArr.find((s: any) => s.key === channelKey) ?? statsArr[0] ?? null)
      : (statsArr[0] ?? null);

  const telegramHref =
    ch?.telegram_username && ch.telegram_username.trim().length > 0
      ? `https://t.me/${ch.telegram_username.replace(/^@/, "")}`
      : null;

  return (
    <main style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <p style={{ marginTop: 0 }}>
        <a href="/" style={{ textDecoration: "underline" }}>← Back to dashboard</a>{" "}
        <span style={{ margin: "0 8px", color: "#bbb" }}>|</span>
        <a href={`/channels/${channelKey}/simulation`} style={{ textDecoration: "underline" }}>
          Open Simulation
        </a>
        <span style={{ margin: "0 8px", color: "#bbb" }}>|</span>
        <a href="/calls" style={{ textDecoration: "underline" }}>Open Calls Explorer</a>
      </p>

      <h1 style={{ marginBottom: 8 }}>Channel: {channelKey || "(missing key!)"}</h1>

      {ch ? (
        <p style={{ marginTop: 0, color: "#444" }}>
          Telegram:{" "}
          {telegramHref ? (
            <a href={telegramHref} target="_blank" rel="noreferrer" style={{ textDecoration: "underline" }}>
              @{ch.telegram_username.replace(/^@/, "")}
            </a>
          ) : (
            <span>(not set)</span>
          )}{" "}
          • enabled: {ch.enabled ? "✅" : "❌"} • live: {ch.live_enabled ? "✅" : "❌"}
        </p>
      ) : (
        <p style={{ marginTop: 0, color: "#444" }}>Telegram: (unknown)</p>
      )}

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
        <h2 style={{ marginBottom: 10 }}>
          Calls (latest 200)
          <span style={{ fontSize: 12, color: "#666", marginLeft: 10 }}>
            Showing calls filtered by channel_key={channelKey || "(none)"}
          </span>
        </h2>

        <div style={{ overflowX: "auto" }}>
          <table cellPadding={10} style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>
                <th>ID</th>
                <th>Mint</th>
                <th>Channel</th>
                <th>Status</th>
                <th>Outcome</th>
                <th>PnL %</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {calls.map((c: any) => {
                const mint: string = typeof c.mint === "string" ? c.mint : "";
                const dexUrl = mint ? dexscreenerSolanaUrl(mint) : null;

                return (
                  <tr key={c.id} style={{ borderBottom: "1px solid #f0f0f0" }}>
                    <td>
                      <a href={`/calls/${c.id}`} style={{ textDecoration: "underline" }}>{c.id}</a>
                    </td>

                    <td style={{ fontFamily: "monospace" }}>
                      {dexUrl ? (
                        <a
                          href={dexUrl}
                          target="_blank"
                          rel="noreferrer"
                          style={{ textDecoration: "underline" }}
                          title="Open Dexscreener"
                        >
                          {mint.slice(0, 6)}…{mint.slice(-6)}
                        </a>
                      ) : (
                        <span style={{ color: "#999" }}>(no mint)</span>
                      )}
                    </td>

                    <td>{c.channel_key}</td>
                    <td>{c.status}</td>
                    <td>{c.outcome ?? ""}</td>
                    <td>{c.pnl_pct != null ? `${Number(c.pnl_pct).toFixed(2)}%` : ""}</td>
                    <td>{new Date(c.started_at).toLocaleString()}</td>
                  </tr>
                );
              })}

              {calls.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ padding: 14, color: "#666" }}>
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

