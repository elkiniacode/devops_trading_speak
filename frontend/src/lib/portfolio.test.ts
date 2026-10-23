import { describe, expect, it } from "vitest";

import { portfolio, position, quote } from "@/test/fixtures";

import { valuePortfolio } from "./portfolio";

describe("valuePortfolio", () => {
  it("values positions at live SSE prices: cash + Σ qty × price", () => {
    const p = portfolio(8000, [position("AAPL", 10, 190, 191), position("MSFT", 2, 400, 410)]);
    const v = valuePortfolio(p, { AAPL: quote("AAPL", 200), MSFT: quote("MSFT", 390) });

    expect(v.positionsValue).toBe(10 * 200 + 2 * 390);
    expect(v.totalValue).toBe(8000 + 2000 + 780);
    expect(v.totalPnl).toBeCloseTo(780);
    expect(v.totalPnlPercent).toBeCloseTo(7.8);
    expect(v.complete).toBe(true);

    const aapl = v.positions.find((x) => x.ticker === "AAPL")!;
    expect(aapl.priceSource).toBe("live");
    expect(aapl.unrealized_pnl).toBe(100); // (200 - 190) × 10
    expect(aapl.unrealized_pnl_percent).toBeCloseTo(5.263, 3); // (200 - 190) / 190
    expect(aapl.weight).toBeCloseTo(2000 / 2780);

    const msft = v.positions.find((x) => x.ticker === "MSFT")!;
    expect(msft.unrealized_pnl).toBe(-20);
    expect(msft.unrealized_pnl_percent).toBeCloseTo(-2.5);
  });

  it("falls back to the REST price, then to cost basis", () => {
    const p = portfolio(1000, [position("AAPL", 1, 100, 120), position("XYZ", 3, 50, null)]);
    const v = valuePortfolio(p, {});

    const aapl = v.positions.find((x) => x.ticker === "AAPL")!;
    expect(aapl.priceSource).toBe("rest");
    expect(aapl.price).toBe(120);

    const xyz = v.positions.find((x) => x.ticker === "XYZ")!;
    expect(xyz.priceSource).toBe("cost");
    expect(xyz.market_value).toBe(150);
    expect(xyz.unrealized_pnl).toBe(0);

    expect(v.totalValue).toBe(1000 + 120 + 150);
    expect(v.complete).toBe(false);
  });

  it("reports total P&L against the $10,000 start with no positions", () => {
    const v = valuePortfolio(portfolio(10000, []), {});
    expect(v.totalValue).toBe(10000);
    expect(v.totalPnl).toBe(0);
    expect(v.positions).toEqual([]);
  });
});
