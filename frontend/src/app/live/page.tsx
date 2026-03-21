// frontend/src/app/live/page.tsx
import { getLiveQueue, getWallet } from "../../lib/api";
import LiveMonitor from "./LiveMonitor";

export default async function LivePage() {
  const [rows, wallet] = await Promise.all([
    getLiveQueue({ limit: 100 }),
    getWallet().catch(() => null),
  ]);

  return (
    <main style={{ padding: "24px 28px 48px", fontFamily: "system-ui, sans-serif", maxWidth: 1200, margin: "0 auto" }}>
      {/* Page header */}
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: "0 0 4px" }}>Live Monitor</h1>
        <p style={{ margin: 0, color: "#6b7280", fontSize: 13 }}>
          Auto-refreshes every 3s · Shows signal→buy and hold→sell timing
        </p>
      </div>

      <LiveMonitor initialRows={rows} initialWallet={wallet} />
    </main>
  );
}
