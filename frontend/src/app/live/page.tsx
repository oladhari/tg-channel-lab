// frontend/src/app/live/page.tsx
import { getLiveQueue, getWallet } from "../../lib/api";
import LiveMonitor from "./LiveMonitor";

export default async function LivePage() {
  const [rows, wallet] = await Promise.all([
    getLiveQueue({ limit: 100 }),
    getWallet().catch(() => null),
  ]);

  return (
    <main style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 4 }}>
        <h1 style={{ margin: 0 }}>Live Monitor</h1>
        <a href="/" style={{ fontSize: 13, color: "#888", textDecoration: "underline" }}>
          ← Dashboard
        </a>
      </div>
      <p style={{ marginTop: 4, color: "#666", fontSize: 13 }}>
        Auto-refreshes every 3s. Shows signal→buy and hold→sell timing.
      </p>

      {/* Wallet bar */}
      <div style={{ display: "flex", gap: 24, padding: "10px 16px", background: "#f0f7ff", borderRadius: 10, marginBottom: 16, flexWrap: "wrap", alignItems: "center" }}>
        <span style={{ fontWeight: 600 }}>
          {wallet?.sol_balance != null ? `${wallet.sol_balance} SOL` : "—"}
        </span>
        <span style={{ color: "#666", fontSize: 12, fontFamily: "monospace" }}>
          {wallet?.pubkey ? `${wallet.pubkey.slice(0, 8)}…${wallet.pubkey.slice(-8)}` : "no key"}
        </span>
        <span style={{ color: "#444" }}>Buys: <b>{wallet?.total_buys ?? "—"}</b></span>
        <span style={{ color: "#444" }}>Sells: <b>{wallet?.total_sells ?? "—"}</b></span>
        <span style={{ color: wallet?.holding ? "#d97706" : "#444" }}>
          Holding: <b>{wallet?.holding ?? "—"}</b>
        </span>
        <span style={{ marginLeft: "auto", fontSize: 12, color: "#888" }}>
          {wallet?.live_channels?.length
            ? `Live: ${wallet.live_channels.map((c: any) => c.key).join(", ")}`
            : "No channels live"}
        </span>
      </div>

      <LiveMonitor initialRows={rows} />
    </main>
  );
}
