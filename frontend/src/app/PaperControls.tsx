// frontend/src/app/PaperControls.tsx
"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

function numOr(v: string | null, fallback: number): number {
  if (v == null || v === "") return fallback;
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function makeStrategyKey(tp: number, sl: number) {
  return `tp${tp}_sl${sl}`;
}

export default function PaperControls() {
  const router = useRouter();
  const sp = useSearchParams();

  const initial = useMemo(() => {
    const tp = numOr(sp.get("tp"), 35);
    const sl = numOr(sp.get("sl"), 20);
    const start = numOr(sp.get("start"), 1.0);
    const entry = numOr(sp.get("entry"), 0.1);
    return { tp, sl, start, entry };
  }, [sp]);

  const [tp, setTp] = useState(initial.tp);
  const [sl, setSl] = useState(initial.sl);
  const [start, setStart] = useState(initial.start);
  const [entry, setEntry] = useState(initial.entry);

  function apply() {
    const qs = new URLSearchParams(sp.toString());
    qs.set("tp", String(tp));
    qs.set("sl", String(sl));
    qs.set("start", String(start));
    qs.set("entry", String(entry));
    router.push(`?${qs.toString()}`);
    router.refresh();
  }

  const strategy_key = makeStrategyKey(tp, sl);

  return (
    <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 14, marginTop: 18 }}>
      <h3 style={{ marginTop: 0 }}>📌 Paper Simulation Controls</h3>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(160px, 1fr))", gap: 10 }}>
        <label style={{ display: "grid", gap: 6 }}>
          <span style={{ fontSize: 12, color: "#555" }}>Start balance (SOL)</span>
          <input value={start} onChange={(e) => setStart(Number(e.target.value))} type="number" step="0.01" />
        </label>

        <label style={{ display: "grid", gap: 6 }}>
          <span style={{ fontSize: 12, color: "#555" }}>Entry size (SOL)</span>
          <input value={entry} onChange={(e) => setEntry(Number(e.target.value))} type="number" step="0.01" />
        </label>

        <label style={{ display: "grid", gap: 6 }}>
          <span style={{ fontSize: 12, color: "#555" }}>TP %</span>
          <input value={tp} onChange={(e) => setTp(Number(e.target.value))} type="number" step="1" />
        </label>

        <label style={{ display: "grid", gap: 6 }}>
          <span style={{ fontSize: 12, color: "#555" }}>SL %</span>
          <input value={sl} onChange={(e) => setSl(Number(e.target.value))} type="number" step="1" />
        </label>
      </div>

      <div style={{ marginTop: 10, fontSize: 12, color: "#555" }}>
        strategy_key: <b>{strategy_key}</b>
      </div>

      <div style={{ display: "flex", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
        <button onClick={apply}>Apply</button>
        <button onClick={() => { setTp(20); setSl(10); }}>tp20/sl10</button>
        <button onClick={() => { setTp(30); setSl(20); }}>tp30/sl20</button>
        <button onClick={() => { setTp(35); setSl(20); }}>tp35/sl20</button>
        <button onClick={() => { setTp(50); setSl(25); }}>tp50/sl25</button>
      </div>
    </div>
  );
}
