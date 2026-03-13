// frontend/src/app/channels/[key]/settings/page.tsx
"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  getChannels,
  toggleChannelLive,
  updateChannel,
  type Channel,
} from "../../../../lib/api";

const GLOBAL_DEFAULT_TP = 35;
const GLOBAL_DEFAULT_SL = 20;

export default function ChannelSettingsPage() {
  const params = useParams<{ key: string }>();
  const channelKey = typeof params?.key === "string" ? params.key : "";
  const router = useRouter();

  const [channel, setChannel] = useState<Channel | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Editable fields
  const [buyAmount, setBuyAmount] = useState("0.1");
  const [tpPct, setTpPct] = useState("");
  const [slPct, setSlPct] = useState("");

  useEffect(() => {
    if (!channelKey) return;
    getChannels()
      .then((channels) => {
        const ch = channels.find((c) => c.key === channelKey) ?? null;
        setChannel(ch);
        if (ch) {
          setBuyAmount(String(ch.live_buy_amount_sol ?? 0.1));
          setTpPct(ch.live_tp_pct != null ? String(ch.live_tp_pct) : "");
          setSlPct(ch.live_sl_pct != null ? String(ch.live_sl_pct) : "");
        }
      })
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [channelKey]);

  async function handleToggleLive() {
    if (!channel) return;
    setSaving(true);
    setErr(null);
    try {
      const updated = await toggleChannelLive(channel.id);
      setChannel(updated);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleSave() {
    if (!channel) return;
    setSaving(true);
    setErr(null);
    setSaved(false);
    try {
      const tp = tpPct.trim() ? Number(tpPct) : null;
      const sl = slPct.trim() ? Number(slPct) : null;
      const updated = await updateChannel(channel.id, {
        live_buy_amount_sol: Number(buyAmount),
        live_tp_pct: tp,
        live_sl_pct: sl,
      });
      setChannel(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setSaving(false);
    }
  }

  function handleClearTpSl() {
    setTpPct("");
    setSlPct("");
  }

  if (!channelKey) {
    return (
      <main style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
        <p style={{ color: "crimson" }}>Missing channel key in URL.</p>
      </main>
    );
  }

  return (
    <main style={{ padding: 24, fontFamily: "system-ui, sans-serif", maxWidth: 640 }}>
      <p style={{ marginTop: 0 }}>
        <Link href={`/channels/${channelKey}`} style={{ textDecoration: "underline" }}>
          ← Back to channel
        </Link>
        <span style={{ margin: "0 8px", color: "#bbb" }}>|</span>
        <Link href={`/channels/${channelKey}/simulation`} style={{ textDecoration: "underline" }}>
          Open Simulation
        </Link>
      </p>

      <h1 style={{ marginBottom: 4 }}>Settings: {channelKey}</h1>
      <p style={{ marginTop: 0, color: "#666", fontSize: 13 }}>
        Configure live trading parameters for this channel.
      </p>

      {loading && <p style={{ color: "#888" }}>Loading…</p>}
      {!loading && !channel && (
        <p style={{ color: "crimson" }}>Channel not found: {channelKey}</p>
      )}

      {channel && (
        <>
          {/* Live toggle */}
          <section style={{ border: "1px solid #ddd", borderRadius: 10, padding: 16, marginBottom: 16 }}>
            <h3 style={{ marginTop: 0, marginBottom: 10 }}>Live Trading</h3>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <span
                style={{
                  display: "inline-block",
                  padding: "4px 10px",
                  borderRadius: 6,
                  fontSize: 13,
                  fontWeight: 600,
                  background: channel.live_enabled ? "#d4edda" : "#f8d7da",
                  color: channel.live_enabled ? "#155724" : "#721c24",
                }}
              >
                {channel.live_enabled ? "LIVE ON" : "LIVE OFF"}
              </span>
              <button onClick={handleToggleLive} disabled={saving}>
                {channel.live_enabled ? "Turn OFF live" : "Turn ON live"}
              </button>
            </div>
            <p style={{ marginTop: 8, marginBottom: 0, fontSize: 12, color: "#888" }}>
              When ON, new calls from this channel will trigger real buys/sells on Solana.
            </p>
          </section>

          {/* Buy amount + TP/SL */}
          <section style={{ border: "1px solid #ddd", borderRadius: 10, padding: 16, marginBottom: 16 }}>
            <h3 style={{ marginTop: 0, marginBottom: 12 }}>Trade Parameters</h3>

            <div style={{ display: "grid", gap: 12 }}>
              <label style={{ display: "grid", gap: 4 }}>
                <span style={{ fontSize: 12, color: "#555" }}>
                  Buy amount (SOL) — how much SOL to spend per call
                </span>
                <input
                  type="number"
                  step="0.01"
                  min="0.001"
                  value={buyAmount}
                  onChange={(e) => setBuyAmount(e.target.value)}
                  style={{ maxWidth: 180 }}
                />
              </label>

              <div>
                <div style={{ fontSize: 12, color: "#555", marginBottom: 4 }}>
                  Take Profit % &amp; Stop Loss % — leave empty to use global default
                  ({GLOBAL_DEFAULT_TP}% TP / {GLOBAL_DEFAULT_SL}% SL)
                </div>
                <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                  <label style={{ display: "grid", gap: 4 }}>
                    <span style={{ fontSize: 12, color: "#555" }}>TP %</span>
                    <input
                      type="number"
                      step="1"
                      min="1"
                      placeholder={`${GLOBAL_DEFAULT_TP} (default)`}
                      value={tpPct}
                      onChange={(e) => setTpPct(e.target.value)}
                      style={{ width: 130 }}
                    />
                  </label>
                  <label style={{ display: "grid", gap: 4 }}>
                    <span style={{ fontSize: 12, color: "#555" }}>SL %</span>
                    <input
                      type="number"
                      step="1"
                      min="1"
                      placeholder={`${GLOBAL_DEFAULT_SL} (default)`}
                      value={slPct}
                      onChange={(e) => setSlPct(e.target.value)}
                      style={{ width: 130 }}
                    />
                  </label>
                </div>

                {(tpPct || slPct) && (
                  <div style={{ marginTop: 6, fontSize: 12, color: "#555" }}>
                    Active:{" "}
                    <b>
                      TP {tpPct || GLOBAL_DEFAULT_TP}% / SL {slPct || GLOBAL_DEFAULT_SL}%
                    </b>{" "}
                    → strategy key:{" "}
                    <code>tp{tpPct || GLOBAL_DEFAULT_TP}_sl{slPct || GLOBAL_DEFAULT_SL}</code>
                  </div>
                )}
                {!tpPct && !slPct && (
                  <div style={{ marginTop: 6, fontSize: 12, color: "#888" }}>
                    Using global default:{" "}
                    <code>tp{GLOBAL_DEFAULT_TP}_sl{GLOBAL_DEFAULT_SL}</code>
                  </div>
                )}
              </div>
            </div>

            <div style={{ display: "flex", gap: 10, marginTop: 16, flexWrap: "wrap", alignItems: "center" }}>
              <button onClick={handleSave} disabled={saving}>
                {saving ? "Saving…" : "Save settings"}
              </button>
              {(tpPct || slPct) && (
                <button onClick={handleClearTpSl} disabled={saving} style={{ color: "#666" }}>
                  Reset to global default
                </button>
              )}
              {saved && (
                <span style={{ color: "green", fontSize: 13 }}>✓ Saved</span>
              )}
            </div>

            {err && (
              <div style={{ marginTop: 10, color: "crimson", fontSize: 13, whiteSpace: "pre-wrap" }}>
                {err}
              </div>
            )}
          </section>

          {/* Quick links */}
          <section style={{ border: "1px solid #ddd", borderRadius: 10, padding: 16 }}>
            <h3 style={{ marginTop: 0, marginBottom: 10 }}>Quick links</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <Link
                href={`/channels/${channelKey}/simulation`}
                style={{ textDecoration: "underline", color: "#0066cc" }}
              >
                → Run TP/SL grid simulation for this channel
              </Link>
              <Link
                href={`/channels/${channelKey}?tp=${tpPct || GLOBAL_DEFAULT_TP}&sl=${slPct || GLOBAL_DEFAULT_SL}`}
                style={{ textDecoration: "underline", color: "#0066cc" }}
              >
                → View paper stats with current TP/SL settings
              </Link>
            </div>
          </section>
        </>
      )}
    </main>
  );
}
