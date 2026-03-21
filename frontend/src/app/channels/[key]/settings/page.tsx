// frontend/src/app/channels/[key]/settings/page.tsx
"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  getChannels,
  toggleChannelLive,
  updateChannel,
  type Channel,
} from "../../../../lib/api";

const S = {
  page:    { padding: "24px 28px 48px", fontFamily: "system-ui, sans-serif", maxWidth: 1200, margin: "0 auto" } as const,
  card:    { padding: 20, background: "#f8faff", border: "1px solid #dbeafe", borderRadius: 12 } as const,
  cardDark:{ padding: 20, background: "#fff", border: "1px solid #e5e7eb", borderRadius: 12 } as const,
  label:   { fontSize: 11, color: "#6b7280", textTransform: "uppercase" as const, letterSpacing: "0.06em", marginBottom: 2 },
  stat:    { fontSize: 26, fontWeight: 700, letterSpacing: "-0.5px", lineHeight: 1 } as const,
  th:      { padding: "10px 12px", textAlign: "left" as const, fontSize: 12, color: "#6b7280", textTransform: "uppercase" as const, letterSpacing: "0.05em", borderBottom: "1px solid #e5e7eb", whiteSpace: "nowrap" as const },
  td:      { padding: "11px 12px", fontSize: 13, borderBottom: "1px solid #f3f4f6", verticalAlign: "middle" as const },
  badge:   (color: string) => ({ display: "inline-block", padding: "2px 8px", borderRadius: 6, fontSize: 11, fontWeight: 600, background: color + "18", color }) as const,
  pill:    (ok: boolean) => ({ display: "inline-block", padding: "2px 8px", borderRadius: 20, fontSize: 11, fontWeight: 600, background: ok ? "#dcfce7" : "#fee2e2", color: ok ? "#15803d" : "#b91c1c" }) as const,
};

const inputStyle = { padding: "6px 10px", border: "1px solid #d1d5db", borderRadius: 6, fontSize: 13, width: "100%" } as const;
const btnPrimary = { padding: "8px 16px", borderRadius: 8, background: "#1d4ed8", color: "#fff", border: "none", fontWeight: 600, fontSize: 13, cursor: "pointer" } as const;
const btnSecondary = { padding: "8px 16px", borderRadius: 8, background: "#f3f4f6", color: "#374151", border: "1px solid #e5e7eb", fontSize: 13, cursor: "pointer" } as const;

export default function ChannelSettingsPage() {
  const params = useParams<{ key: string }>();
  const channelKey = typeof params?.key === "string" ? params.key : "";
  const [channel, setChannel] = useState<Channel | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [bestStat, setBestStat] = useState<any>(null);

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

  useEffect(() => {
    if (!channelKey) return;
    fetch(`/api/stats/best?start_balance_sol=1&entry_sol=0.1`)
      .then((r) => r.json())
      .then((arr: any[]) => {
        const found = arr.find((s) => s.key === channelKey);
        setBestStat(found ?? null);
      })
      .catch(() => null);
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
      <main style={{ maxWidth: 800, margin: "0 auto", padding: "24px 28px 48px", fontFamily: "system-ui, sans-serif" }}>
        <p style={{ color: "crimson" }}>Missing channel key in URL.</p>
      </main>
    );
  }

  return (
    <main style={{ maxWidth: 800, margin: "0 auto", padding: "24px 28px 48px", fontFamily: "system-ui, sans-serif" }}>
      {/* Breadcrumb */}
      <div style={{ fontSize: 12, color: "#9ca3af", marginBottom: 12 }}>
        <Link href="/" style={{ color: "#6b7280", textDecoration: "none" }}>Dashboard</Link>
        <span style={{ margin: "0 6px" }}>/</span>
        <Link href={`/channels/${channelKey}`} style={{ color: "#6b7280", textDecoration: "none" }}>{channelKey}</Link>
        <span style={{ margin: "0 6px" }}>/</span>
        <span style={{ color: "#374151" }}>Settings</span>
      </div>

      <h1 style={{ fontSize: 22, fontWeight: 700, margin: "0 0 4px" }}>Settings: {channelKey}</h1>
      <p style={{ marginTop: 0, marginBottom: 20, color: "#6b7280", fontSize: 13 }}>
        Configure live trading parameters for this channel.
      </p>

      {loading && <p style={{ color: "#9ca3af" }}>Loading…</p>}
      {!loading && !channel && (
        <p style={{ color: "crimson" }}>Channel not found: {channelKey}</p>
      )}

      {channel && (
        <>
          {/* Live toggle */}
          <section style={{ ...S.cardDark, marginBottom: 16 }}>
            <h3 style={{ marginTop: 0, marginBottom: 10, fontSize: 15, fontWeight: 600 }}>Live Trading</h3>
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <span style={S.pill(channel.live_enabled)}>
                {channel.live_enabled ? "LIVE ON" : "LIVE OFF"}
              </span>
              <button
                style={{
                  padding: "7px 14px",
                  borderRadius: 8,
                  fontSize: 13,
                  fontWeight: 500,
                  background: channel.live_enabled ? "#fee2e2" : "#dcfce7",
                  color: channel.live_enabled ? "#b91c1c" : "#15803d",
                  border: "1px solid currentColor",
                  cursor: "pointer",
                }}
                onClick={handleToggleLive}
                disabled={saving}
              >
                {channel.live_enabled ? "Turn OFF live" : "Turn ON live"}
              </button>
            </div>
            <p style={{ marginTop: 8, marginBottom: 0, fontSize: 12, color: "#9ca3af" }}>
              When ON, new calls from this channel will trigger real buys/sells on Solana.
            </p>
          </section>

          {/* Buy amount + TP/SL */}
          <section style={{ ...S.cardDark, marginBottom: 16 }}>
            <h3 style={{ marginTop: 0, marginBottom: 12, fontSize: 15, fontWeight: 600 }}>Trade Parameters</h3>

            <div style={{ display: "grid", gap: 12 }}>
              <label style={{ display: "grid", gap: 4 }}>
                <span style={{ fontSize: 12, color: "#6b7280" }}>
                  Buy amount (SOL) — how much SOL to spend per call
                </span>
                <input
                  style={{ ...inputStyle, maxWidth: 180 }}
                  type="number"
                  step="0.01"
                  min="0.001"
                  value={buyAmount}
                  onChange={(e) => setBuyAmount(e.target.value)}
                />
              </label>

              <div>
                <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>
                  Take Profit % &amp; Stop Loss % — leave empty to use global default (35% TP / 20% SL)
                </div>

                {bestStat && (
                  <div style={{ fontSize: 12, color: "#1e40af", background: "#eff6ff", border: "1px solid #bfdbfe", borderRadius: 6, padding: "6px 10px", marginBottom: 8 }}>
                    Suggested by grid: <b>TP {bestStat.best_tp_pct}% / SL {bestStat.best_sl_pct}%</b> (from grid simulation)
                  </div>
                )}

                <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                  <label style={{ display: "grid", gap: 4 }}>
                    <span style={{ fontSize: 12, color: "#6b7280" }}>TP %</span>
                    <input
                      style={{ ...inputStyle, width: 130 }}
                      type="number"
                      step="1"
                      min="1"
                      placeholder="35 (default)"
                      value={tpPct}
                      onChange={(e) => setTpPct(e.target.value)}
                    />
                  </label>
                  <label style={{ display: "grid", gap: 4 }}>
                    <span style={{ fontSize: 12, color: "#6b7280" }}>SL %</span>
                    <input
                      style={{ ...inputStyle, width: 130 }}
                      type="number"
                      step="1"
                      min="1"
                      placeholder="20 (default)"
                      value={slPct}
                      onChange={(e) => setSlPct(e.target.value)}
                    />
                  </label>
                </div>

                {(tpPct || slPct) && (
                  <div style={{ marginTop: 6, fontSize: 12, color: "#6b7280" }}>
                    Active:{" "}
                    <b>
                      TP {tpPct || "35"}% / SL {slPct || "20"}%
                    </b>{" "}
                    → strategy key:{" "}
                    <code>tp{tpPct || "35"}_sl{slPct || "20"}</code>
                  </div>
                )}
                {!tpPct && !slPct && (
                  <div style={{ marginTop: 6, fontSize: 12, color: "#9ca3af" }}>
                    {bestStat
                      ? <>Suggested by grid: <b>TP {bestStat.best_tp_pct}% / SL {bestStat.best_sl_pct}%</b></>
                      : <>Using global default: <code>tp35_sl20</code></>
                    }
                  </div>
                )}
              </div>
            </div>

            <div style={{ display: "flex", gap: 10, marginTop: 16, flexWrap: "wrap", alignItems: "center" }}>
              <button style={btnPrimary} onClick={handleSave} disabled={saving}>
                {saving ? "Saving…" : "Save settings"}
              </button>
              {(tpPct || slPct) && (
                <button style={btnSecondary} onClick={handleClearTpSl} disabled={saving}>
                  Reset to global default
                </button>
              )}
              {saved && (
                <span style={{ color: "#16a34a", fontSize: 13, fontWeight: 600 }}>✓ Saved</span>
              )}
            </div>

            {err && (
              <div style={{ marginTop: 10, color: "crimson", fontSize: 13, whiteSpace: "pre-wrap" }}>
                {err}
              </div>
            )}
          </section>

          {/* Quick links */}
          <section style={{ ...S.cardDark }}>
            <h3 style={{ marginTop: 0, marginBottom: 10, fontSize: 15, fontWeight: 600 }}>Quick links</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <Link
                href={`/channels/${channelKey}/simulation`}
                style={{ textDecoration: "none", color: "#1d4ed8", fontSize: 13 }}
              >
                → Run TP/SL grid simulation for this channel
              </Link>
              <Link
                href={`/channels/${channelKey}`}
                style={{ textDecoration: "none", color: "#1d4ed8", fontSize: 13 }}
              >
                → View channel calls and best-strategy stats
              </Link>
            </div>
          </section>
        </>
      )}
    </main>
  );
}
