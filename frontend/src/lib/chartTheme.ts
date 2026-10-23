import { ColorType, CrosshairMode, type DeepPartial, type ChartOptions, LineStyle, type UTCTimestamp } from "lightweight-charts";

/** Colors mirrored from globals.css; the canvas can't read CSS variables. */
export const CHART_COLORS = {
  text: "#8b95ad",
  grid: "rgba(33, 43, 66, 0.55)",
  border: "#212b42",
  crosshair: "#5c6680",
  primary: "#209dd7",
  accent: "#ecad0a",
  gain: "#2fc48c",
  loss: "#f2575c",
} as const;

export const baseChartOptions: DeepPartial<ChartOptions> = {
  autoSize: true,
  layout: {
    background: { type: ColorType.Solid, color: "transparent" },
    textColor: CHART_COLORS.text,
    fontFamily: '"Archivo Variable", ui-sans-serif, system-ui, sans-serif',
    fontSize: 11,
  },
  grid: {
    vertLines: { color: CHART_COLORS.grid },
    horzLines: { color: CHART_COLORS.grid },
  },
  rightPriceScale: { borderColor: CHART_COLORS.border },
  timeScale: { borderColor: CHART_COLORS.border, timeVisible: true, secondsVisible: true },
  crosshair: {
    mode: CrosshairMode.Magnet,
    vertLine: { color: CHART_COLORS.crosshair, style: LineStyle.Dashed, labelBackgroundColor: "#2f3a57" },
    horzLine: { color: CHART_COLORS.crosshair, style: LineStyle.Dashed, labelBackgroundColor: "#2f3a57" },
  },
  handleScroll: false,
  handleScale: false,
};

/**
 * Lightweight Charts renders UTCTimestamp values as UTC. Shift unix seconds by the local
 * offset so axis labels read in the viewer's time zone.
 */
export function toChartTime(unixSeconds: number): UTCTimestamp {
  const offsetSeconds = -new Date(unixSeconds * 1000).getTimezoneOffset() * 60;
  return (unixSeconds + offsetSeconds) as UTCTimestamp;
}
