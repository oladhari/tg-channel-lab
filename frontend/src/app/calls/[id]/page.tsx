// frontend/src/app/calls/[id]/page.tsx
import { getCall, getCallPrices } from "../../../lib/api";
import PriceChart from "./PriceChart";
import { gmgnSolanaTokenUrl } from "../../../lib/links";

type Props = {
  params: any; // can be object OR Promise in some Next versions
};

export default async function CallDetailPage(props: Props) {
  const params = await Promise.resolve(props.params);
  const idRaw = params?.id;
  const id = Number(typeof idRaw === "string" ? idRaw : "");

  if (!Number.isFinite(id) || id <= 0) {
    return (
      <main style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
        <h1 style={{ marginBottom: 8 }}>Invalid Call ID</h1>
        <p style={{ color: "#444" }}>
          Got: <code>{String(idRaw)}</code>
        </p>
        <a href="/calls" style={{ textDecoration: "underline" }}>
          ← Back to Calls Explorer
        </a>
      </main>
    );
  }

  const [call, prices] = await Promise.all([getCall(id), getCallPrices(id)]);

  // default strategy
  const sr = call.strategy_results.find((x) => x.strategy_key === "tp35_sl20") ?? null;

  const entryPrice = sr?.entry_price_usd ?? call.entry_price_usd ?? null;
  const exitT = sr?.exit_t_sec ?? null;
  const exitPrice = sr?.exit_price_usd ?? null;

  const tpPrice = sr && entryPrice != null ? entryPrice * (1 + sr.tp_pct / 100) : null;
  const slPrice = sr && entryPrice != null ? entryPrice * (1 - sr.sl_pct / 100) : null;

  return (
    <main style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <h1 style={{ marginBottom: 8 }}>Call #{call.id}</h1>

      <div style={{ marginBottom: 14, color: "#444", lineHeight: 1.7 }}>
        <div><b>Channel:</b> {call.channel_key}</div>

        <div>
          <b>Mint:</b>{" "}
          <a
            href={gmgnSolanaTokenUrl(call.mint)}
            target="_blank"
            rel="noreferrer"
            style={{ textDecoration: "underline", fontFamily: "monospace" }}
            title="Open GMGN"
          >
            {call.mint}
          </a>
        </div>

        <div><b>Status:</b> {call.status}</div>
        <div><b>Started:</b> {new Date(call.started_at).toLocaleString()}</div>

        <div style={{ marginTop: 8 }}>
          <a href="/calls" style={{ textDecoration: "underline", marginRight: 12 }}>
            ← Back
          </a>
          <a
            href={gmgnSolanaTokenUrl(call.mint)}
            target="_blank"
            rel="noreferrer"
            style={{ textDecoration: "underline" }}
          >
            Open GMGN
          </a>
        </div>
      </div>

      <h2 style={{ marginBottom: 10 }}>Price</h2>
      <PriceChart
        prices={prices ?? []}
        entryPrice={entryPrice}
        tpPrice={tpPrice}
        slPrice={slPrice}
        exitT={exitT}
        exitPrice={exitPrice}
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
