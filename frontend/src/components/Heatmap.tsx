"use client";

import { useMemo, useRef } from "react";

import { useElementSize } from "@/hooks/useElementSize";
import { formatMoney, formatPercent, pnlSign } from "@/lib/format";
import { layoutTreemap, pnlColor, PNL_CLAMP } from "@/lib/heatmap";
import type { LivePosition } from "@/lib/portfolio";

import { Panel } from "./Panel";

interface HeatmapProps {
  positions: LivePosition[] | null;
  onSelect: (ticker: string) => void;
}

const FALLBACK_SIZE = { width: 480, height: 220 };

/** Positions as a treemap: area = weight, color = P&L % clamped to ±5% (CONTRACTS R30). */
export function Heatmap({ positions, onSelect }: HeatmapProps) {
  const boxRef = useRef<HTMLDivElement>(null);
  const size = useElementSize(boxRef, FALLBACK_SIZE);

  const tiles = useMemo(() => {
    if (!positions) return [];
    const byTicker = new Map(positions.map((p) => [p.ticker, p]));
    return layoutTreemap(
      positions.map((p) => ({ ticker: p.ticker, value: p.market_value })),
      size.width,
      size.height,
    ).map((rect) => ({ rect, position: byTicker.get(rect.ticker)! }));
  }, [positions, size.width, size.height]);

  const empty = positions !== null && tiles.length === 0;

  return (
    <Panel
      title="Portfolio heatmap"
      meta={`Colored by P&L, ±${PNL_CLAMP}% scale`}
      className="min-h-[200px]"
      bodyClassName="p-1.5"
    >
      <div ref={boxRef} data-testid="heatmap" className="relative h-full w-full">
        {empty && (
          <div
            data-testid="heatmap-empty"
            className="absolute inset-0 flex flex-col items-center justify-center gap-1 rounded-[2px] border border-dashed border-line-strong text-center"
          >
            <span className="text-[13px] font-medium text-muted">No positions yet</span>
            <span className="text-[12px] text-dim">Buy a stock and it appears here, sized by its weight.</span>
          </div>
        )}
        {tiles.map(({ rect, position }) => {
          const sign = pnlSign(position.unrealized_pnl);
          const roomy = (rect.width / 100) * size.width > 64 && (rect.height / 100) * size.height > 40;
          return (
            <button
              key={rect.ticker}
              type="button"
              data-testid={`heatmap-tile-${rect.ticker}`}
              data-pnl-sign={sign}
              onClick={() => onSelect(rect.ticker)}
              title={`${rect.ticker}: ${formatMoney(position.market_value)}, ${(position.weight * 100).toFixed(1)}% of positions, ${formatPercent(position.unrealized_pnl_percent)}`}
              className="heat-tile absolute flex flex-col items-start justify-between overflow-hidden rounded-[2px] p-1.5 text-left text-white hover:brightness-110"
              style={{
                left: `${rect.left}%`,
                top: `${rect.top}%`,
                width: `${rect.width}%`,
                height: `${rect.height}%`,
                backgroundColor: pnlColor(position.unrealized_pnl_percent, sign),
              }}
            >
              <span className="font-wide text-[12.5px] leading-tight font-bold">{rect.ticker}</span>
              {roomy && (
                <span className="tabular text-[11.5px] leading-tight font-medium opacity-90">
                  {formatPercent(position.unrealized_pnl_percent)}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </Panel>
  );
}
