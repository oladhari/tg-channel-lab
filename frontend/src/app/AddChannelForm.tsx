// frontend/src/app/AddChannelForm.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { normalizeTelegramUsername } from "../lib/telegram";
import { createChannel } from "../lib/api";

function toNumOrNull(v: string): number | null {
  const t = v.trim();
  if (!t) return null;
  const n = Number(t);
  if (!Number.isFinite(n)) return null;
  return n;
}

export default function AddChannelForm() {
  const router = useRouter();

  const [input, setInput] = useState("");
  const [liveEnabled, setLiveEnabled] = useState(false); // default false ✅

  // ✅ NEW: per-channel live buy amount (SOL)
  // Default to 0.005 so you can test with low balance
  const [amount, setAmount] = useState("0.005");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const normalized = normalizeTelegramUsername(input);

  async function submit() {
    setError(null);

    if (!normalized) {
      setError("Please enter a valid Telegram username or link.");
      return;
    }

    const parsedAmount = toNumOrNull(amount);
    if (parsedAmount != null) {
      if (parsedAmount <= 0) {
        setError("Live buy amount must be > 0.");
        return;
      }
      // tiny safety guard, optional
      if (parsedAmount > 10) {
        setError("Live buy amount looks too high. Please double-check.");
        return;
      }
    }

    setLoading(true);
    try {
      // ✅ Keep add-channel working via our unified /api/channels route
      // ✅ Include live_buy_amount_sol ONLY if user provided a valid number
      await createChannel({
        key: normalized,
        telegram_username: normalized,
        enabled: true, // recording ON by default ✅
        live_enabled: liveEnabled, // user choice ✅
        live_buy_amount_sol: parsedAmount, // ✅ NEW
      });

      setInput("");
      setLiveEnabled(false);
      setAmount("0.005");

      // refresh Server Component data (channels/stats)
      router.refresh();
    } catch (e: any) {
      setError(e?.message || "Error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 14, marginBottom: 18 }}>
      <h3 style={{ marginTop: 0 }}>➕ Add Telegram Channel</h3>

      <input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="@channel | https://t.me/channel | channel"
        style={{ width: "100%", padding: 10, marginBottom: 8 }}
      />

      {normalized && (
        <div style={{ fontSize: 12, color: "#555", marginBottom: 8 }}>
          Will be saved as: <b>@{normalized}</b>
        </div>
      )}

      <div style={{ display: "flex", gap: 14, flexWrap: "wrap", alignItems: "center", marginBottom: 10 }}>
        <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <input type="checkbox" checked={liveEnabled} onChange={(e) => setLiveEnabled(e.target.checked)} />
          Live enabled (future live trading / alerts)
        </label>

        <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 12, color: "#555" }}>Live buy amount (SOL)</span>
          <input
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            type="number"
            step="0.0001"
            min="0"
            style={{ width: 130, padding: 6 }}
            title="Per-channel live buy size in SOL"
          />
        </label>
      </div>

      {error && <div style={{ color: "crimson", marginBottom: 8 }}>{error}</div>}

      <button onClick={submit} disabled={loading}>
        {loading ? "Adding…" : "Add Channel"}
      </button>
    </div>
  );
}
