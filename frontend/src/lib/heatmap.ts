import { hierarchy, treemap, treemapSquarify } from "d3-hierarchy";

import { type PnlSign, pnlSign } from "./format";

/** P&L % at which a tile reaches full color (CONTRACTS R30). */
export const PNL_CLAMP = 5;

type RGB = [number, number, number];

// Keep in sync with --color-loss / --color-tile / --color-gain in globals.css.
const LOSS: RGB = [214, 64, 69];
const NEUTRAL: RGB = [58, 65, 84];
const GAIN: RGB = [31, 158, 107];

/** Any non-zero P&L gets at least this much tint, so a tile's color always shows its sign. */
const MIN_TINT = 0.18;

function mix(a: RGB, b: RGB, t: number): RGB {
  return [0, 1, 2].map((i) => Math.round(a[i] + (b[i] - a[i]) * t)) as RGB;
}

/**
 * Tile color for a P&L percentage: red at -5% or below, neutral gray at 0, green at +5%
 * or above, linear in between. Returns an `rgb(r, g, b)` string.
 *
 * `sign` decides the hue. It defaults to the sign of the percentage; the heatmap passes the
 * sign of the dollar P&L so a tile's color always agrees with its `data-pnl-sign`.
 */
export function pnlColor(pnlPercent: number, sign: PnlSign = pnlSign(pnlPercent)): string {
  const pct = Number.isFinite(pnlPercent) ? pnlPercent : 0;
  let rgb = NEUTRAL;
  if (sign !== "zero") {
    const strength = Math.min(Math.abs(pct) / PNL_CLAMP, 1);
    const t = MIN_TINT + (1 - MIN_TINT) * strength;
    rgb = mix(NEUTRAL, sign === "positive" ? GAIN : LOSS, t);
  }
  return `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`;
}

export interface TileInput {
  ticker: string;
  value: number;
}

export interface TileRect {
  ticker: string;
  /** Position and size as percentages of the container. */
  left: number;
  top: number;
  width: number;
  height: number;
}

/**
 * Squarified treemap of the inputs, sized by value, laid out for a container of the given
 * pixel size and returned in percentages so tiles stay put while the container resizes.
 */
export function layoutTreemap(items: TileInput[], width: number, height: number, gap = 2): TileRect[] {
  const usable = items.filter((i) => i.value > 0);
  if (usable.length === 0 || width <= 0 || height <= 0) return [];
  const root = hierarchy<{ children?: TileInput[]; ticker?: string; value?: number }>({ children: usable })
    .sum((d) => (d.children ? 0 : (d.value ?? 0)))
    .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
  treemap<{ children?: TileInput[]; ticker?: string; value?: number }>()
    .tile(treemapSquarify)
    .size([width, height])
    .paddingInner(gap)
    .round(false)(root);
  return root.leaves().map((leaf) => {
    const node = leaf as typeof leaf & { x0: number; y0: number; x1: number; y1: number };
    return {
      ticker: leaf.data.ticker ?? "",
      left: (node.x0 / width) * 100,
      top: (node.y0 / height) * 100,
      width: ((node.x1 - node.x0) / width) * 100,
      height: ((node.y1 - node.y0) / height) * 100,
    };
  });
}
