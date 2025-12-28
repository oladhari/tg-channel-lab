"use client";

import type { PricePoint } from "../../../lib/api";

type Props = {
  prices: PricePoint[];
  entryPrice?: number | null;
  tpPrice?: number | null;
  slPrice?: number | null;
  exitT?: number | null;
  exitPrice?: number | null;
};

export default function CallChart({
  prices,
  entryPrice,
  tpPrice,
  slPrice,
  exitT,
  exitPrice,
}: Props) {
  const w = 900;
  const h = 260;
  const pad = 14;

  if (!prices || prices.length < 2) {
    return <p style={{ color: "#666" }}>Not enough price points yet.</p>;
  }

  const xs = prices.map((p) => p.t_sec);
  const ys = prices.map((p) => p.price_usd);

  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);

  const xOf = (t: number) => {
    if (maxX === minX) return pad;
    const r = (t - minX) / (maxX - minX);
    return pad + r * (w - 2 * pad);
  };

  const yOf = (p: number) => {
    if (maxY === minY) return h / 2;
    const r = (p - minY) / (maxY - minY);
    return (h - pad) - r * (h - 2 * pad);
  };

  const path = prices
    .map((p, i) => `${i === 0 ? "M" : "L"} ${xOf(p.t_sec).toFixed(2)} ${yOf(p.price_usd).toFixed(2)}`)
    .join(" ");

  const HLine = ({ price, dashed, label }: { price: number; dashed?: string; label: string }) => (
    <>
      <line
        x1={pad}
        x2={w - pad}
        y1={yOf(price)}
        y2={yOf(price)}
        stroke="currentColor"
        strokeDasharray={dashed ?? ""}
        opacity={0.25}
      />
      <text x={pad + 6} y={yOf(price) - 6} fontSize="11" fill="currentColor" opacity={0.55}>
        {label}
      </text>
    </>
  );

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${w} ${h}`}
      style={{ border: "1px solid #e5e5e5", borderRadius: 8 }}
    >
      {/* price line */}
      <path d={path} fill="none" stroke="currentColor" strokeWidth="1.5" />

      {/* markers */}
      {entryPrice != null && <HLine price={entryPrice} dashed="4 4" label="Entry" />}
      {tpPrice != null && <HLine price={tpPrice} dashed="2 6" label="TP" />}
      {slPrice != null && <HLine price={slPrice} dashed="2 6" label="SL" />}

      {/* exit point */}
      {exitT != null && exitPrice != null && (
        <circle cx={xOf(exitT)} cy={yOf(exitPrice)} r="4" fill="currentColor" opacity={0.85} />
      )}
    </svg>
  );
}
