// frontend/src/app/calls/[id]/PriceChart.tsx
"use client";

import { useEffect, useMemo, useRef } from "react";
import { createChart, type UTCTimestamp } from "lightweight-charts";

type PricePoint = { t_sec: number; price_usd: number };

type Props = {
  prices: PricePoint[];
  entryPrice: number | null;
  tpPrice: number | null;
  slPrice: number | null;
  exitT: number | null;
  exitPrice: number | null;
};

export default function PriceChart({
  prices,
  entryPrice,
  tpPrice,
  slPrice,
  exitT,
  exitPrice,
}: Props) {
  const ref = useRef<HTMLDivElement | null>(null);

  const safePrices: PricePoint[] = Array.isArray(prices) ? prices : [];

  // chart expects unix timestamps
  const base = 1700000000;

  const lineData = useMemo(() => {
    return safePrices
      .filter((p) => Number.isFinite(p?.t_sec) && Number.isFinite(p?.price_usd))
      .map((p) => ({
        time: (base + p.t_sec) as UTCTimestamp,
        value: p.price_usd,
      }));
  }, [safePrices]);

  const timeRange = useMemo(() => {
    if (lineData.length === 0) return null;
    return { first: lineData[0].time, last: lineData[lineData.length - 1].time };
  }, [lineData]);

  const markers = useMemo(() => {
    if (!timeRange) return [];

    const m: any[] = [];

    if (entryPrice != null && Number.isFinite(entryPrice)) {
      m.push({
        time: timeRange.first,
        position: "belowBar",
        shape: "arrowUp",
        text: `BUY @ ${Number(entryPrice).toFixed(8)}`,
      });
    }

    if (
      exitT != null &&
      Number.isFinite(exitT) &&
      exitPrice != null &&
      Number.isFinite(exitPrice)
    ) {
      m.push({
        time: (base + exitT) as UTCTimestamp,
        position: "aboveBar",
        shape: "arrowDown",
        text: `SELL @ ${Number(exitPrice).toFixed(8)}`,
      });
    }

    return m;
  }, [entryPrice, exitT, exitPrice, timeRange]);

  useEffect(() => {
    if (!ref.current) return;

    // empty state
    if (lineData.length === 0) {
      ref.current.innerHTML =
        `<div style="padding:12px;color:#666;border:1px solid #eee;border-radius:12px;">No price points yet.</div>`;
      return;
    } else {
      ref.current.innerHTML = "";
    }

    const chart = createChart(ref.current, {
      width: ref.current.clientWidth,
      height: 340,
      layout: { textColor: "#111" },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
      grid: {
        vertLines: { visible: true },
        horzLines: { visible: true },
      },
    });

    const priceSeries = chart.addLineSeries();
    priceSeries.setData(lineData);
    // @ts-expect-error markers typing differs across versions
    priceSeries.setMarkers(markers);

    // TP/SL horizontal lines (drawn as separate line series)
    if (timeRange && tpPrice != null && Number.isFinite(tpPrice)) {
      const tpSeries = chart.addLineSeries();
      tpSeries.setData([
        { time: timeRange.first, value: tpPrice },
        { time: timeRange.last, value: tpPrice },
      ]);
    }

    if (timeRange && slPrice != null && Number.isFinite(slPrice)) {
      const slSeries = chart.addLineSeries();
      slSeries.setData([
        { time: timeRange.first, value: slPrice },
        { time: timeRange.last, value: slPrice },
      ]);
    }

    chart.timeScale().fitContent();

    const onResize = () => {
      if (!ref.current) return;
      chart.applyOptions({ width: ref.current.clientWidth });
    };
    window.addEventListener("resize", onResize);

    return () => {
      window.removeEventListener("resize", onResize);
      chart.remove();
    };
  }, [lineData, markers, tpPrice, slPrice, timeRange]);

  return <div ref={ref} />;
}
