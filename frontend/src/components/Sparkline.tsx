import type { PricePoint } from "@/lib/priceStore";

interface SparklineProps {
  ticker: string;
  points: PricePoint[];
  width?: number;
  height?: number;
}

/** Points for an SVG polyline scaled into the box, or "" with fewer than two prices. */
export function sparklinePath(points: PricePoint[], width: number, height: number, pad = 1.5): string {
  if (points.length < 2) return "";
  let min = Infinity;
  let max = -Infinity;
  for (const p of points) {
    if (p.price < min) min = p.price;
    if (p.price > max) max = p.price;
  }
  const span = max - min || 1;
  const step = (width - pad * 2) / (points.length - 1);
  return points
    .map((p, i) => {
      const x = pad + i * step;
      const y = max === min ? height / 2 : pad + (1 - (p.price - min) / span) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

/** Price action since page load, drawn from the SSE buffer. Colored by net move. */
export function Sparkline({ ticker, points, width = 64, height = 22 }: SparklineProps) {
  const path = sparklinePath(points, width, height);
  const first = points[0]?.price;
  const last = points[points.length - 1]?.price;
  const stroke =
    first === undefined || last === undefined || last === first
      ? "var(--color-muted)"
      : last > first
        ? "var(--color-gain)"
        : "var(--color-loss)";

  return (
    <svg
      data-testid={`sparkline-${ticker}`}
      data-points={points.length}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
      className="block"
    >
      {path ? (
        <polyline points={path} fill="none" stroke={stroke} strokeWidth="1.25" strokeLinejoin="round" />
      ) : (
        <line
          x1="0"
          x2={width}
          y1={height / 2}
          y2={height / 2}
          stroke="var(--color-line-strong)"
          strokeDasharray="2 3"
        />
      )}
    </svg>
  );
}
