import type { Portfolio, PriceMap } from "./types";

export const STARTING_CASH = 10_000;

/** Where a position's price came from: the SSE stream, the last REST response, or cost basis. */
export type PriceSource = "live" | "rest" | "cost";

export interface LivePosition {
  ticker: string;
  quantity: number;
  avg_cost: number;
  price: number;
  priceSource: PriceSource;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_percent: number;
  /** Share of total positions value, 0..1. */
  weight: number;
}

export interface LiveValuation {
  cash: number;
  positions: LivePosition[];
  positionsValue: number;
  totalValue: number;
  totalPnl: number;
  totalPnlPercent: number;
  /** False when any position fell back to its cost basis because it has no price. */
  complete: boolean;
}

/**
 * Value the portfolio with live SSE prices (CONTRACTS R17/R18):
 * total = cash + Σ qty × price, where price falls back to the REST current_price
 * and then to avg_cost (flagged via priceSource / complete).
 */
export function valuePortfolio(portfolio: Portfolio, prices: PriceMap): LiveValuation {
  let positionsValue = 0;
  let complete = true;
  const rows = portfolio.positions.map((p) => {
    const live = prices[p.ticker]?.price;
    let price: number;
    let priceSource: PriceSource;
    if (typeof live === "number") {
      price = live;
      priceSource = "live";
    } else if (typeof p.current_price === "number") {
      price = p.current_price;
      priceSource = "rest";
    } else {
      price = p.avg_cost;
      priceSource = "cost";
      complete = false;
    }
    const market_value = p.quantity * price;
    const unrealized_pnl = (price - p.avg_cost) * p.quantity;
    const unrealized_pnl_percent = p.avg_cost ? ((price - p.avg_cost) / p.avg_cost) * 100 : 0;
    positionsValue += market_value;
    return {
      ticker: p.ticker,
      quantity: p.quantity,
      avg_cost: p.avg_cost,
      price,
      priceSource,
      market_value,
      unrealized_pnl,
      unrealized_pnl_percent,
      weight: 0,
    };
  });
  for (const row of rows) row.weight = positionsValue > 0 ? row.market_value / positionsValue : 0;

  const totalValue = portfolio.cash_balance + positionsValue;
  const totalPnl = totalValue - STARTING_CASH;
  return {
    cash: portfolio.cash_balance,
    positions: rows,
    positionsValue,
    totalValue,
    totalPnl,
    totalPnlPercent: (totalPnl / STARTING_CASH) * 100,
    complete,
  };
}
