import { getCall, getCallPrices } from "../../../lib/api";
import CallChart from "./CallChart";

function dexscreenerUrl(mint: string) {
  return `https://dexscreener.com/solana/${mint}`;
}

export default async function CallDetailPage({ params }: { params: { id: string } }) {
  const id = Number(params.id);

  const [call, prices] = await Promise.all([getCall(id), getCallPrices(id)]);

  const sr = call.strategy_results.find((x) => x.strategy_key === "tp35_sl20") ?? null;

  const entry = sr?.entry_price_usd ?? call.entry_price_usd ?? null;
  const tpPrice = sr && entry != null ? entry * (1 + sr.tp_pct / 100) : null;
  const slPrice = sr && entry != null ? entry * (1 - sr.sl_pct / 100) : null;

  return (
    <main style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <h1 style={{ marginBottom: 8 }}>Call #{call.id}</h1>

      <div style={{ marginBottom: 14, color: "#444", lineHeight: 1.7 }}>
        <div><b>Channel:</b> {call.channel_key}</div>
        <div><b>Mint:</b> {call.mint}</div>
        <div><b>Status:</b> {call.status}</div>
        <div><b>Started:</b> {new Date(call.started_at).toLocaleString()}</div>
        <div>
          <a href="/calls" style={{ textDecoration: "underline", marginRight: 12 }}>← Back</a>
          <a href={dexscreenerUrl(call.mint)} target="_blank" rel="noreferrer" style={{ textDecoration: "underline" }}>
            Open Dexscreener
          </a>
        </div>
      </div>

      <h2 style={{ marginBottom: 10 }}>Price</h2>
      <CallChart
        prices={prices}
        entryPrice={entry}
        tpPrice={tpPrice}
        slPrice={slPrice}
        exitT={sr?.exit_t_sec ?? null}
        exitPrice={sr?.exit_price_usd ?? null}
      />

      <h2 style={{ margin: "18px 0 10px" }}>Strategy Results</h2>
      <div style={{ overflowX: "auto" }}>
        <table cellPadding={10} style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid #ddd" }}>
              <th>strategy_key</th>
              <th>outcome</th>
              <th>pnl_pct</th>
              <th>exit_t_sec</th>
              <th>exit_price_usd</th>
            </tr>
          </thead>
          <tbody>
            {call.strategy_results.map((r) => (
              <tr key={r.strategy_key} style={{ borderBottom: "1px solid #f0f0f0" }}>
                <td>{r.strategy_key}</td>
                <td>{r.outcome}</td>
                <td>{Number(r.pnl_pct).toFixed(2)}%</td>
                <td>{r.exit_t_sec ?? ""}</td>
                <td>{r.exit_price_usd ?? ""}</td>
              </tr>
            ))}
            {call.strategy_results.length === 0 && (
              <tr>
                <td colSpan={5} style={{ padding: 14, color: "#666" }}>
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
