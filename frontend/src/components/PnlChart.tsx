"use client";

import { BaselineSeries, createChart, type IChartApi, type ISeriesApi } from "lightweight-charts";
import { useEffect, useMemo, useRef } from "react";

import { baseChartOptions, CHART_COLORS, toChartTime } from "@/lib/chartTheme";
import { formatMoney, formatSignedMoney, pnlSign } from "@/lib/format";
import { STARTING_CASH } from "@/lib/portfolio";
import type { Snapshot } from "@/lib/types";

import { Panel } from "./Panel";
import { SIGN_TEXT } from "./tone";

/** Snapshots as chart points: unix seconds, ascending, one per second (the last one wins). */
export function snapshotPoints(snapshots: Snapshot[]): { time: number; value: number }[] {
  const out: { time: number; value: number }[] = [];
  for (const s of snapshots) {
    const ms = Date.parse(s.recorded_at);
    if (Number.isNaN(ms)) continue;
    const time = Math.floor(ms / 1000);
    const last = out[out.length - 1];
    if (last && last.time === time) last.value = s.total_value;
    else if (!last || time > last.time) out.push({ time, value: s.total_value });
  }
  return out;
}

interface PnlChartProps {
  snapshots: Snapshot[] | null;
  /** Live total, shown in the title bar. */
  liveTotal: number | null;
}

/**
 * Total portfolio value over time from portfolio_snapshots, green above $10k and red below.
 * `data-points` counts the recorded snapshots only, not the live tail point.
 */
export function PnlChart({ snapshots, liveTotal }: PnlChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Baseline"> | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const chart = createChart(container, {
      ...baseChartOptions,
      timeScale: { ...baseChartOptions.timeScale, secondsVisible: false },
      localization: { priceFormatter: (price: number) => formatMoney(price) },
    });
    seriesRef.current = chart.addSeries(BaselineSeries, {
      baseValue: { type: "price", price: STARTING_CASH },
      topLineColor: CHART_COLORS.gain,
      topFillColor1: "rgba(47, 196, 140, 0.24)",
      topFillColor2: "rgba(47, 196, 140, 0.02)",
      bottomLineColor: CHART_COLORS.loss,
      bottomFillColor1: "rgba(242, 87, 92, 0.02)",
      bottomFillColor2: "rgba(242, 87, 92, 0.24)",
      lineWidth: 2,
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
      crosshairMarkerRadius: 3,
    });
    chartRef.current = chart;
    return () => {
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  const points = useMemo(() => (snapshots ? snapshotPoints(snapshots) : null), [snapshots]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series || !points) return;
    series.setData(points.map((p) => ({ time: toChartTime(p.time), value: p.value })));
    chartRef.current?.timeScale().fitContent();
  }, [points]);

  // Extend the line to the live total so it ends where the header does. The next refetch's
  // setData drops this point again in favor of the recorded snapshots.
  useEffect(() => {
    const series = seriesRef.current;
    if (!series || !points || points.length === 0 || liveTotal === null) return;
    const now = Math.floor(Date.now() / 1000);
    if (now <= points[points.length - 1].time) return;
    try {
      series.update({ time: toChartTime(now), value: liveTotal });
      chartRef.current?.timeScale().fitContent();
    } catch {
      // out-of-order time (e.g. a clock change); the next snapshot refresh resets the data
    }
  }, [points, liveTotal]);

  const count = snapshots?.length ?? 0;
  const pnl = liveTotal === null ? null : liveTotal - STARTING_CASH;

  return (
    <Panel
      title="Portfolio value"
      meta={pnl === null ? undefined : <span className={SIGN_TEXT[pnlSign(pnl)]}>{formatSignedMoney(pnl)} total</span>}
      className="min-h-0"
    >
      <div ref={containerRef} data-testid="pnl-chart" data-points={count} className="absolute inset-0 px-1 pt-1" />
      {snapshots !== null && count < 2 && (
        <div className="pointer-events-none absolute inset-x-0 bottom-3 text-center text-[12px] text-dim">
          A new point is recorded every 30 seconds and after each trade.
        </div>
      )}
    </Panel>
  );
}
