// frontend/src/app/ChannelRowActions.tsx
"use client";

import { useEffect, useState } from "react";
import { setChannelLiveBuyAmount, toggleChannelEnabled, toggleChannelLive } from "../lib/api";

type Props = {
  id: number;
  enabled: boolean;
  live_enabled: boolean;

  // ✅ NEW
  live_buy_amount_sol?: number | null;
};

export default function ChannelRowActions({ id, enabled, live_enabled, live_buy_amount_sol }: Props) {
  const [loading, setLoading] = useState<null | "enabled" | "live" | "amount">(null);
  const [err, setErr] = useState<string | null>(null);

  // local editor state
  const [editing, setEditing] = useState(false);
  const [amount, setAmount] = useState<string>("");

  useEffect(() => {
    // keep input in sync with server value
    const v = live_buy_amount_sol;
    setAmount(v == null ? "" : String(v));
  }, [live_buy_amount_sol]);

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

  async function onSaveAmount() {
    setErr(null);
    setLoading("amount");

    // allow empty => null (fallback to env/default in workers)
    const trimmed = amount.trim();
    let val: number | null = null;

    if (trimmed !== "") {
      const n = Number(trimmed);
      if (!Number.isFinite(n) || n <= 0) {
        setErr("Amount must be a number > 0 (or empty).");
        setLoading(null);
        return;
      }
      // optional safety
      if (n > 10) {
        setErr("Amount looks too high. Please double-check.");
        setLoading(null);
        return;
      }
      val = n;
    }

    try {
      await setChannelLiveBuyAmount(id, val);
      setEditing(false);
      window.location.reload();
    } catch (e: any) {
      setErr(e?.message ?? "Failed to update amount");
    } finally {
      setLoading(null);
    }
  }

  function onCancelEdit() {
    setEditing(false);
    const v = live_buy_amount_sol;
    setAmount(v == null ? "" : String(v));
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

      {/* ✅ NEW: Live buy amount editor */}
      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <span style={{ fontSize: 12, color: "#666" }} title="Per-channel live buy size (SOL)">
          Buy:
        </span>

        {!editing ? (
          <>
            <span style={{ fontSize: 12 }}>
              <b>{live_buy_amount_sol == null ? "default" : live_buy_amount_sol}</b>
              <span style={{ fontSize: 12, color: "#666" }}> SOL</span>
            </span>

            <button
              onClick={() => setEditing(true)}
              disabled={loading !== null}
              style={{
                padding: "4px 8px",
                border: "1px solid #ddd",
                borderRadius: 8,
                cursor: loading ? "not-allowed" : "pointer",
                background: "#fff",
              }}
              title="Edit live buy amount for this channel"
            >
              Edit
            </button>
          </>
        ) : (
          <>
            <input
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              type="number"
              step="0.0001"
              min="0"
              style={{ width: 110, padding: "4px 6px", border: "1px solid #ddd", borderRadius: 8 }}
              placeholder="0.005"
              disabled={loading !== null}
              title="Empty = use default (.env)"
            />

            <button
              onClick={onSaveAmount}
              disabled={loading !== null}
              style={{
                padding: "4px 8px",
                border: "1px solid #ddd",
                borderRadius: 8,
                cursor: loading ? "not-allowed" : "pointer",
                background: "#111",
                color: "#fff",
              }}
              title="Save"
            >
              {loading === "amount" ? "..." : "Save"}
            </button>

            <button
              onClick={onCancelEdit}
              disabled={loading !== null}
              style={{
                padding: "4px 8px",
                border: "1px solid #ddd",
                borderRadius: 8,
                cursor: loading ? "not-allowed" : "pointer",
                background: "#fff",
              }}
              title="Cancel"
            >
              Cancel
            </button>
          </>
        )}
      </div>

      {err && <span style={{ color: "crimson", fontSize: 12 }}>{err}</span>}
    </div>
  );
}
