"use client";

import { CandlestickSeries, HistogramSeries, LineSeries, createChart, type IChartApi, type ISeriesApi, type SeriesType } from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";
import { atr, ema, macd, rsi, sma } from "@/lib/indicators";
import type { Candle, MarketMode } from "@/lib/types";
import type { PricePoint } from "@/lib/priceStore";
import type { PriceUpdate } from "@/lib/types";
import { baseChartOptions, toChartTime } from "@/lib/chartTheme";
import { formatPercent, formatPrice, pnlSign } from "@/lib/format";
import { SIGN_TEXT } from "./tone";
import { ChartDrawings } from "./ChartDrawings";

const TIMEFRAMES = ["M1", "M5", "M15", "H1", "H4", "D1"] as const;
const TIMEFRAME_SECONDS: Record<(typeof TIMEFRAMES)[number], number> = { M1: 60, M5: 300, M15: 900, H1: 3600, H4: 14400, D1: 86400 };
const INDICATORS = ["SMA20", "SMA50", "EMA21", "EMA50", "VOL", "RSI14", "MACD"] as const;
type Indicator = (typeof INDICATORS)[number];

interface MainChartProps {
  ticker: string | null;
  quote: PriceUpdate | null | undefined;
  points: PricePoint[];
  mode: MarketMode | null;
  levels?: { entry?: number; stopLoss?: number | null; takeProfit?: number | null; pending?: number[] };
}

export function MainChart({ ticker, quote, points, mode, levels }: MainChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | ISeriesApi<"Line"> | null>(null);
  const indicatorsRef = useRef<ISeriesApi<SeriesType>[]>([]);
  const predictionTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const [timeframe, setTimeframe] = useState<(typeof TIMEFRAMES)[number]>("H1");
  const [kind, setKind] = useState<"candles" | "line">("line");
  const [candles, setCandles] = useState<Candle[]>([]);
  const [sourceLabel, setSourceLabel] = useState("");
  const [enabled, setEnabled] = useState<Indicator[]>(["SMA20", "VOL"]);
  const [prediction, setPrediction] = useState<{ candles: Candle[]; target: number; tolerance: number; count: number; finished: boolean } | null>(null);
  const [target, setTarget] = useState("");
  const [crosshair, setCrosshair] = useState<Candle | null>(null);
  const shown = prediction?.candles ?? candles;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const chart = createChart(container, {
      ...baseChartOptions,
      layout: { background: { color: "#0d1211" }, textColor: "#8b9491", fontFamily: "JetBrains Mono, monospace" },
      grid: { vertLines: { color: "#1f2523" }, horzLines: { color: "#1f2523" } },
      rightPriceScale: { borderColor: "#2a312f" }, timeScale: { borderColor: "#2a312f", timeVisible: true },
    });
    chartRef.current = chart;
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(([entry]) => chart.applyOptions({ width: Math.floor(entry.contentRect.width), height: Math.floor(entry.contentRect.height) }));
    observer?.observe(container);
    return () => { observer?.disconnect(); chart.remove(); chartRef.current = null; seriesRef.current = null; indicatorsRef.current = []; };
  }, []);

  useEffect(() => {
    if (!ticker) { setCandles([]); return; }
    let cancelled = false;
    api.candles(ticker, timeframe).then((result) => {
      if (!cancelled) { setCandles(result.candles); setSourceLabel(result.synthetic ? "SIMULACIÓN" : "DATOS DISPONIBLES"); }
    }).catch(() => { if (!cancelled) { setCandles([]); setSourceLabel("SIN HISTORIAL"); } });
    return () => { cancelled = true; };
  }, [ticker, timeframe]);

  useEffect(() => {
    if (predictionTimer.current) clearInterval(predictionTimer.current);
    predictionTimer.current = null;
    setPrediction(null);
  }, [ticker, timeframe]);
  useEffect(() => () => { if (predictionTimer.current) clearInterval(predictionTimer.current); }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    if (seriesRef.current) chart.removeSeries?.(seriesRef.current);
    const series = kind === "candles"
      ? chart.addSeries(CandlestickSeries, { upColor: "#5eead4", downColor: "#ff7a7a", borderUpColor: "#5eead4", borderDownColor: "#ff7a7a", wickUpColor: "#5eead4", wickDownColor: "#ff7a7a" })
      : chart.addSeries(LineSeries, { color: "#18a8e0", lineWidth: 2 });
    seriesRef.current = series as ISeriesApi<"Candlestick">;
    if (kind === "candles") {
      (series as ISeriesApi<"Candlestick">).setData(shown.map((c) => ({ time: toChartTime(c.time), open: c.open, high: c.high, low: c.low, close: c.close })));
    } else {
      (series as ISeriesApi<"Line">).setData(shown.map((c) => ({ time: toChartTime(c.time), value: c.close })));
    }
    chart.timeScale().fitContent();
  }, [shown, kind]);

  const calculated = useMemo(() => {
    const close = candles.map((c) => c.close);
    return { SMA20: sma(close, 20), SMA50: sma(close, 50), EMA21: ema(close, 21), EMA50: ema(close, 50), RSI14: rsi(close), MACD: macd(close) };
  }, [candles]);

  useEffect(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!chart?.subscribeClick || !series?.coordinateToPrice) return;
    const onClick = (event: { point?: { y: number } | null }) => {
      if (prediction || event.point == null) return;
      const price = series.coordinateToPrice(event.point.y);
      if (price != null && Number.isFinite(Number(price)) && Number(price) > 0) setTarget(Number(price).toFixed(2));
    };
    chart.subscribeClick(onClick);
    return () => chart.unsubscribeClick(onClick);
  }, [prediction, candles, kind]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    for (const series of indicatorsRef.current) chart.removeSeries?.(series);
    indicatorsRef.current = [];
    if (!candles.length) return;
    const addLine = (values: Array<number | null>, color: string, pane = 0) => {
      const series = chart.addSeries(LineSeries, { color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, pane);
      series.setData(values.flatMap((value, index) => value === null ? [] : [{ time: toChartTime(candles[index].time), value }]));
      indicatorsRef.current.push(series as ISeriesApi<SeriesType>);
    };
    if (enabled.includes("SMA20")) addLine(calculated.SMA20, "#22d3ee");
    if (enabled.includes("SMA50")) addLine(calculated.SMA50, "#a78bfa");
    if (enabled.includes("EMA21")) addLine(calculated.EMA21, "#f5a524");
    if (enabled.includes("EMA50")) addLine(calculated.EMA50, "#ff2bd6");
    let pane = 1;
    if (enabled.includes("VOL")) {
      const series = chart.addSeries(HistogramSeries, { color: "#23564c", priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false }, pane++);
      series.setData(candles.map((c) => ({ time: toChartTime(c.time), value: c.volume, color: c.close >= c.open ? "#23564c" : "#5b3033" })));
      indicatorsRef.current.push(series as ISeriesApi<SeriesType>);
    }
    if (enabled.includes("RSI14")) addLine(calculated.RSI14, "#a78bfa", pane++);
    if (enabled.includes("MACD")) {
      addLine(calculated.MACD.line, "#22d3ee", pane);
      addLine(calculated.MACD.signal, "#f5a524", pane);
      const series = chart.addSeries(HistogramSeries, { color: "#5eead4", priceLineVisible: false, lastValueVisible: false }, pane);
      series.setData(calculated.MACD.histogram.flatMap((value, index) => value === null ? [] : [{ time: toChartTime(candles[index].time), value, color: value >= 0 ? "#23564c" : "#5b3033" }]));
      indicatorsRef.current.push(series as ISeriesApi<SeriesType>);
    }
    chart.timeScale().fitContent();
  }, [candles, calculated, enabled]);

  useEffect(() => {
    if (!quote || !seriesRef.current || prediction) return;
    const second = Math.floor(Date.parse(quote.timestamp) / 1000);
    if (!Number.isFinite(second) || second <= 0) return;
    const last = candles[candles.length - 1];
    const bucket = Math.floor(second / TIMEFRAME_SECONDS[timeframe]) * TIMEFRAME_SECONDS[timeframe];
    if (kind === "candles") {
      const candle = last && Math.floor(last.time / TIMEFRAME_SECONDS[timeframe]) * TIMEFRAME_SECONDS[timeframe] === bucket
        ? { time: toChartTime(last.time), open: last.open, high: Math.max(last.high, quote.price), low: Math.min(last.low, quote.price), close: quote.price }
        : { time: toChartTime(bucket), open: quote.previous_price, high: Math.max(quote.previous_price, quote.price), low: Math.min(quote.previous_price, quote.price), close: quote.price };
      try { (seriesRef.current as ISeriesApi<"Candlestick">).update(candle); } catch { /* a late event is replaced by the next candle refresh */ }
    } else {
      try { (seriesRef.current as ISeriesApi<"Line">).update({ time: toChartTime(bucket), value: quote.price }); } catch { /* ignore a late tick */ }
    }
  }, [quote, kind, candles, timeframe, prediction]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series?.createPriceLine) return;
    const lines = [
      { value: quote?.price, color: "#18a8e0", title: "ACTUAL" },
      { value: levels?.entry, color: "#22d3ee", title: "ENTRADA" },
      { value: levels?.stopLoss, color: "#ff7a7a", title: "SL" },
      { value: levels?.takeProfit, color: "#5eead4", title: "TP" },
      ...(levels?.pending ?? []).slice(0, 10).map((value) => ({ value, color: "#f5a524", title: "ORDEN" })),
    ].filter((line): line is { value: number; color: string; title: string } => line.value != null);
    const handles = lines.map((line) => series.createPriceLine({ price: line.value, color: line.color, lineWidth: 1, axisLabelVisible: false, title: line.title }));
    return () => handles.forEach((handle) => series.removePriceLine(handle));
  }, [quote?.price, levels, kind]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart?.subscribeCrosshairMove) return;
    const onMove = (param: { time?: unknown }) => {
      const timestamp = Number(param.time);
      const found = candles.find((c) => toChartTime(c.time) === timestamp);
      setCrosshair(found ?? null);
    };
    chart.subscribeCrosshairMove(onMove);
    return () => chart.unsubscribeCrosshairMove(onMove);
  }, [candles]);

  function startPrediction() {
    if (candles.length < 15 || predictionTimer.current) return;
    const last = candles[candles.length - 1];
    const chosen = Number(target || last.close);
    if (!Number.isFinite(chosen) || chosen <= 0) return;
    const tolerance = atr(candles) || last.close * 0.005;
    let count = 0;
    setPrediction({ candles: candles.map((c) => ({ ...c })), target: chosen, tolerance, count: 0, finished: false });
    predictionTimer.current = setInterval(() => {
      count++;
      setPrediction((previous) => {
        if (!previous) return null;
        const prior = previous.candles[previous.candles.length - 1];
        const delta = Math.sin(count * 7.21 + (ticker?.length ?? 0)) * previous.tolerance * 0.8;
        const close = Math.max(0.01, prior.close + delta);
        const next: Candle = { time: prior.time + TIMEFRAME_SECONDS[timeframe], open: prior.close, high: Math.max(prior.close, close), low: Math.min(prior.close, close), close, volume: 0 };
        return { ...previous, candles: [...previous.candles, next], count, finished: count >= 10 };
      });
      if (count >= 10 && predictionTimer.current) { clearInterval(predictionTimer.current); predictionTimer.current = null; }
    }, 700);
  }

  function endPrediction() {
    if (predictionTimer.current) clearInterval(predictionTimer.current);
    predictionTimer.current = null;
    setPrediction(null);
  }

  const sign = quote ? pnlSign(quote.change_percent) : "zero";
  const baseline = mode === "simulator" ? "desde el inicio de sesión" : "vs. cierre anterior";
  const readout = crosshair ?? shown[shown.length - 1];
  const predictionHit = prediction?.finished ? Math.abs(prediction.candles[prediction.candles.length - 1].close - prediction.target) <= prediction.tolerance : null;

  return (
    <section className="flex min-h-[330px] flex-1 flex-col overflow-hidden rounded-[4px] border border-line bg-panel">
      <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-line px-3 py-2">
        <h2 className="font-heading text-[23px] font-bold text-accent">{ticker ?? "—"}</h2>
        {quote && <><span className="tabular text-[20px] font-bold">{formatPrice(quote.price)}</span><span className={`tabular text-[12px] ${SIGN_TEXT[sign]}`}>{formatPercent(quote.change_percent)}</span></>}
        <span className="hidden text-[10px] text-muted xl:inline">{baseline}</span>
        <div className="ml-auto flex flex-wrap gap-1" aria-label="Intervalo del gráfico">
          {TIMEFRAMES.map((tf) => <button key={tf} onClick={() => setTimeframe(tf)} className={`rounded border px-2 py-1 text-[10px] ${timeframe === tf ? "border-accent text-accent" : "border-line text-muted"}`}>{tf}</button>)}
          <button onClick={() => setKind((v) => v === "candles" ? "line" : "candles")} className="ml-1 rounded border border-line-strong px-2 py-1 text-[10px] text-fg">{kind === "candles" ? "VELAS" : "LÍNEA"}</button>
        </div>
      </header>
      <div className="flex shrink-0 flex-wrap gap-1 border-b border-line px-3 py-1.5" aria-label="Indicadores">{INDICATORS.map((item) => <button key={item} aria-pressed={enabled.includes(item)} onClick={() => setEnabled((old) => old.includes(item) ? old.filter((value) => value !== item) : [...old, item])} className={`rounded border px-2 py-0.5 text-[9px] ${enabled.includes(item) ? "border-accent text-accent" : "border-line text-muted"}`}>{item}</button>)}<span className="ml-auto text-[9px] text-dim">{sourceLabel}</span></div>
      <ChartDrawings ticker={ticker} timeframe={timeframe} chart={chartRef.current} series={seriesRef.current} container={containerRef.current} />
      <div className="flex shrink-0 gap-3 border-b border-line px-3 py-1 text-[9px] text-muted"><span>O {readout ? formatPrice(readout.open) : "—"}</span><span>H {readout ? formatPrice(readout.high) : "—"}</span><span>L {readout ? formatPrice(readout.low) : "—"}</span><span>C {readout ? formatPrice(readout.close) : "—"}</span><span className="ml-auto">VOL {readout?.volume ?? "—"}</span></div>
      <div className="relative min-h-0 flex-1">
        <div ref={containerRef} data-testid="main-chart" data-ticker={ticker ?? ""} data-points={points.length} className="absolute inset-0" />
        {candles.length === 0 && <div className="pointer-events-none absolute inset-0 flex items-center justify-center text-[12px] text-muted">{ticker ? `Cargando velas de ${ticker}…` : "Selecciona una acción de la lista."}</div>}
      </div>
      <div className="flex shrink-0 items-center gap-2 border-t border-line px-3 py-1.5 text-[9px]"><strong className="text-primary">PREDECIR</strong><span className="hidden text-muted lg:inline">Elige objetivo en el gráfico o ingresa el precio</span><label className="text-muted">OBJETIVO <input aria-label="Precio objetivo" type="number" min="0" step="any" value={target} onChange={(event) => setTarget(event.target.value)} placeholder={quote?.price.toFixed(2) ?? "Precio"} className="ml-1 w-20 rounded border border-line-strong bg-ink px-1.5 py-1 text-fg" /></label>{[0.98, 0.99, 1.01, 1.02].map((factor) => <button key={factor} disabled={!quote || !!prediction} onClick={() => setTarget(((quote?.price ?? 0) * factor).toFixed(2))} className="rounded border border-line px-1.5 py-1 text-muted">{factor < 1 ? "−" : "+"}{Math.round(Math.abs(1 - factor) * 100)}%</button>)}{prediction ? <><span className={predictionHit === null ? "text-muted" : predictionHit ? "text-gain" : "text-loss"}>{prediction.finished ? predictionHit ? "ACIERTO" : "FUERA DE RANGO" : `${prediction.count}/10`}</span><button onClick={endPrediction} className="ml-auto rounded border border-line px-2 py-1">CERRAR</button></> : <button disabled={candles.length < 15} onClick={startPrediction} className="ml-auto rounded border border-primary bg-primary/10 px-2 py-1 font-bold text-primary disabled:opacity-40">PREDECIR</button>}</div>
    </section>
  );
}
