// frontend/src/app/ChannelRowActions.tsx
"use client";

import { useState } from "react";
import { toggleChannelEnabled, toggleChannelLive } from "../lib/api";

type Props = {
  id: number;
  enabled: boolean;
  live_enabled: boolean;
};

export default function ChannelRowActions({ id, enabled, live_enabled }: Props) {
  const [loading, setLoading] = useState<null | "enabled" | "live">(null);
  const [err, setErr] = useState<string | null>(null);

  async function onToggleEnabled() {
    setErr(null);
    setLoading("enabled");
    try {
      await toggleChannelEnabled(id);
      window.location.reload();
    } catch (e: any) {
      setErr(e?.message ?? "Failed to toggle enabled");
    } finally {
      setLoading(null);
    }
  }

  async function onToggleLive() {
    setErr(null);
    setLoading("live");
    try {
      await toggleChannelLive(id);
      window.location.reload();
    } catch (e: any) {
      setErr(e?.message ?? "Failed to toggle live");
    } finally {
      setLoading(null);
    }
  }

  return (
    <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
      <button
        onClick={onToggleEnabled}
        disabled={loading !== null}
        style={{
          padding: "6px 10px",
          border: "1px solid #ddd",
          borderRadius: 8,
          cursor: loading ? "not-allowed" : "pointer",
          background: enabled ? "#fff" : "#111",
          color: enabled ? "#111" : "#fff",
        }}
        title="Toggle recording/listening for this channel"
      >
        {loading === "enabled" ? "..." : enabled ? "Disable" : "Enable"}
      </button>

      <button
        onClick={onToggleLive}
        disabled={loading !== null || !enabled}
        style={{
          padding: "6px 10px",
          border: "1px solid #ddd",
          borderRadius: 8,
          cursor: loading || !enabled ? "not-allowed" : "pointer",
          background: live_enabled ? "#0b5" : "#fff",
          color: live_enabled ? "#fff" : "#111",
          opacity: enabled ? 1 : 0.5,
        }}
        title={!enabled ? "Enable the channel first" : "Toggle live selling (GMGN) for this channel"}
      >
        {loading === "live" ? "..." : live_enabled ? "Live ON" : "Live OFF"}
      </button>

      {err && <span style={{ color: "crimson", fontSize: 12 }}>{err}</span>}
    </div>
  );
}
