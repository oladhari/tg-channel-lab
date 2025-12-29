// frontend/src/app/AddChannelForm.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { normalizeTelegramUsername } from "../lib/telegram";

export default function AddChannelForm() {
  const router = useRouter();

  const [input, setInput] = useState("");
  const [liveEnabled, setLiveEnabled] = useState(false); // default false ✅
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const normalized = normalizeTelegramUsername(input);

  async function submit() {
    setError(null);

    if (!normalized) {
      setError("Please enter a valid Telegram username or link.");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch("/api/channels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          key: normalized,
          telegram_username: normalized,
          enabled: true, // recording ON by default ✅
          live_enabled: liveEnabled, // user choice ✅
        }),
      });

      if (!res.ok) {
        const ct = res.headers.get("content-type") || "";
        if (ct.includes("application/json")) {
          const j = await res.json().catch(() => null);
          const msg = j?.detail || j?.message || JSON.stringify(j);
          throw new Error(msg || `Request failed (${res.status})`);
        } else {
          const text = await res.text();
          throw new Error(`Request failed (${res.status}). ${text.slice(0, 200)}...`);
        }
      }

      setInput("");
      setLiveEnabled(false);

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

      <label style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <input type="checkbox" checked={liveEnabled} onChange={(e) => setLiveEnabled(e.target.checked)} />
        Live enabled (future live trading / alerts)
      </label>

      {error && <div style={{ color: "crimson", marginBottom: 8 }}>{error}</div>}

      <button onClick={submit} disabled={loading}>
        {loading ? "Adding…" : "Add Channel"}
      </button>
    </div>
  );
}
