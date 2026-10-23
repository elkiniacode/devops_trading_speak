"use client";

import type { IChartApi, ISeriesApi, UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef, useState, type PointerEvent } from "react";
import { createPortal } from "react-dom";

type Tool = "select" | "support" | "resistance" | "trend" | "zone" | "measure";
type Drawing = { id: string; kind: Exclude<Tool, "select">; t1: number; p1: number; t2: number; p2: number };
type PriceSeries = ISeriesApi<"Candlestick"> | ISeriesApi<"Line">;

function parseSaved(raw: string | null): Drawing[] {
  if (!raw) return [];
  try {
    const data: unknown = JSON.parse(raw);
    if (!data || typeof data !== "object" || (data as { version?: number }).version !== 1) return [];
    const items = (data as { drawings?: unknown }).drawings;
    if (!Array.isArray(items)) return [];
    return items.slice(0, 100).filter((item): item is Drawing => item && typeof item.id === "string" &&
      ["support", "resistance", "trend", "zone", "measure"].includes(item.kind) &&
      [item.t1, item.p1, item.t2, item.p2].every((number) => typeof number === "number" && Number.isFinite(number)));
  } catch { return []; }
}

export function ChartDrawings({ ticker, timeframe, chart, series, container }: { ticker: string | null; timeframe: string; chart: IChartApi | null; series: PriceSeries | null; container: HTMLDivElement | null }) {
  const [tool, setTool] = useState<Tool>("select");
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [loadedKey, setLoadedKey] = useState("");
  const [first, setFirst] = useState<{ time: number; price: number } | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [, setView] = useState(0);
  const drag = useRef<string | null>(null);
  const frame = useRef<number | null>(null);
  const key = ticker ? `terminal-chart-v1:${ticker}:${timeframe}` : "";

  useEffect(() => {
    setDrawings(key ? parseSaved(localStorage.getItem(key)) : []);
    setLoadedKey(key);
    setFirst(null); setSelected(null); setTool("select");
  }, [key]);
  useEffect(() => {
    if (!key || loadedKey !== key) return;
    const timer = setTimeout(() => localStorage.setItem(key, JSON.stringify({ version: 1, drawings: drawings.slice(-100) })), 300);
    return () => clearTimeout(timer);
  }, [key, loadedKey, drawings]);
  useEffect(() => {
    if (!container) return;
    const update = () => setSize({ width: container.clientWidth, height: container.clientHeight });
    update();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    observer?.observe(container);
    return () => observer?.disconnect();
  }, [container]);
  useEffect(() => {
    if (!chart) return;
    const refresh = () => setView((value) => value + 1);
    chart.timeScale().subscribeVisibleLogicalRangeChange?.(refresh);
    return () => chart.timeScale().unsubscribeVisibleLogicalRangeChange?.(refresh);
  }, [chart]);
  useEffect(() => {
    if (!chart?.subscribeClick || !series || tool === "select") return;
    const onClick = (event: { point?: { y: number }; time?: unknown }) => {
      if (!event.point || event.time == null || !series.coordinateToPrice) return;
      const price = series.coordinateToPrice(event.point.y);
      if (price == null) return;
      const point = { time: Number(event.time), price: Number(price) };
      if (tool === "support" || tool === "resistance") {
        setDrawings((old) => [...old, { id: crypto.randomUUID(), kind: tool, t1: point.time, p1: point.price, t2: point.time, p2: point.price }]);
        setTool("select");
      } else if (!first) setFirst(point);
      else {
        setDrawings((old) => [...old, { id: crypto.randomUUID(), kind: tool, t1: first.time, p1: first.price, t2: point.time, p2: point.price }]);
        setFirst(null); setTool("select");
      }
    };
    chart.subscribeClick(onClick);
    return () => chart.unsubscribeClick(onClick);
  }, [chart, series, tool, first]);
  useEffect(() => () => { if (frame.current !== null) cancelAnimationFrame(frame.current); }, []);

  function pixels(time: number, price: number) {
    if (!chart || !series?.priceToCoordinate) return null;
    const x = chart.timeScale().timeToCoordinate(time as UTCTimestamp);
    const y = series.priceToCoordinate(price);
    return x == null || y == null ? null : { x: Math.round(x), y: Math.round(y) };
  }

  function move(event: PointerEvent<SVGElement>) {
    if (!drag.current || !chart || !series?.coordinateToPrice || frame.current !== null) return;
    const rect = event.currentTarget.ownerSVGElement?.getBoundingClientRect();
    if (!rect) return;
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    frame.current = requestAnimationFrame(() => {
      frame.current = null;
      const time = chart.timeScale().coordinateToTime(x);
      const price = series.coordinateToPrice(y);
      if (time == null || price == null) return;
      setDrawings((old) => old.map((item) => item.id !== drag.current ? item : {
        ...item, t2: item.t2 + Number(time) - item.t1, p2: item.p2 + Number(price) - item.p1,
        t1: Number(time), p1: Number(price),
      }));
    });
  }

  const overlay = container && createPortal(<svg width={size.width} height={size.height} className="absolute inset-0" style={{ pointerEvents: "none" }} aria-label="Dibujos del gráfico">
    {drawings.map((item) => {
      const a = pixels(item.t1, item.p1);
      const b = pixels(item.t2, item.p2);
      if (!a) return null;
      const x2 = b?.x ?? size.width;
      const y2 = b?.y ?? a.y;
      const color = item.kind === "resistance" ? "#ff7a7a" : item.kind === "zone" ? "#a78bfa" : "#5eead4";
      const events = { style: { pointerEvents: "all" as const, cursor: "move" },
        onPointerDown: (event: PointerEvent<SVGElement>) => { drag.current = item.id; setSelected(item.id); event.currentTarget.setPointerCapture(event.pointerId); },
        onPointerMove: move, onPointerUp: () => { drag.current = null; } };
      if (item.kind === "zone") return <rect key={item.id} x={Math.min(a.x, x2)} y={Math.min(a.y, y2)} width={Math.abs(x2 - a.x)} height={Math.abs(y2 - a.y)} fill={`${color}22`} stroke={color} strokeWidth={selected === item.id ? 2 : 1} {...events} />;
      return <g key={item.id}><line x1={item.kind === "support" || item.kind === "resistance" ? 0 : a.x} y1={a.y} x2={item.kind === "support" || item.kind === "resistance" ? size.width : x2} y2={y2} stroke={color} strokeWidth={selected === item.id ? 3 : 2} {...events} />{item.kind === "measure" && <text x={x2} y={y2 - 8} fill={color} fontSize="10">{((item.p2 / item.p1 - 1) * 100).toFixed(2)}%</text>}</g>;
    })}
  </svg>, container);

  return <><div className="flex shrink-0 flex-wrap items-center gap-1 border-b border-line px-3 py-1" aria-label="Herramientas de dibujo">
    {([["select", "SELECCIONAR"], ["support", "SOPORTE"], ["resistance", "RESISTENCIA"], ["trend", "TENDENCIA"], ["zone", "ZONA"], ["measure", "MEDIR"]] as const).map(([value, label]) => <button key={value} aria-pressed={tool === value} onClick={() => { setTool(value); setFirst(null); }} className={`rounded px-1.5 py-0.5 text-[9px] ${tool === value ? "bg-accent/10 text-accent" : "text-muted"}`}>{label}</button>)}
    <button disabled={!selected} onClick={() => { setDrawings((old) => old.filter((item) => item.id !== selected)); setSelected(null); }} className="rounded px-1.5 py-0.5 text-[9px] text-loss disabled:opacity-40">BORRAR</button>
    <button disabled={!drawings.length} onClick={() => { setDrawings([]); setSelected(null); }} className="rounded px-1.5 py-0.5 text-[9px] text-muted disabled:opacity-40">LIMPIAR</button>
    {first && <span className="text-[9px] text-accent">Elige el segundo punto</span>}
  </div>{overlay}</>;
}
