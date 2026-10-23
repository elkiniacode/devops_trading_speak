import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { valuePortfolio } from "@/lib/portfolio";
import { portfolio, position, quote } from "@/test/fixtures";

import { PositionsTable } from "./PositionsTable";

describe("PositionsTable", () => {
  it("shows quantity, cost, live price and P&L for each position", () => {
    const v = valuePortfolio(portfolio(5000, [position("AAPL", 10, 190.12, 190.12), position("NVDA", 0.5, 800, 800)]), {
      AAPL: quote("AAPL", 191.2),
      NVDA: quote("NVDA", 780),
    });
    render(<PositionsTable positions={v.positions} onSelect={() => {}} />);

    expect(screen.getByTestId("positions-table")).toBeInTheDocument();
    expect(screen.getByTestId("position-row-AAPL")).toBeInTheDocument();
    expect(screen.getByTestId("position-qty-AAPL")).toHaveTextContent("10");
    expect(screen.getByTestId("position-avg-cost-AAPL")).toHaveTextContent("$190.12");
    expect(screen.getByTestId("position-price-AAPL")).toHaveTextContent("191.20");
    expect(screen.getByTestId("position-pnl-AAPL")).toHaveTextContent("+$10.80");
    expect(screen.getByTestId("position-pnl-percent-AAPL")).toHaveTextContent("+0.57%");
    expect(screen.getByTestId("position-pnl-AAPL")).toHaveClass("text-gain");

    expect(screen.getByTestId("position-qty-NVDA")).toHaveTextContent("0.5");
    expect(screen.getByTestId("position-pnl-NVDA")).toHaveTextContent("-$10.00");
    expect(screen.getByTestId("position-pnl-percent-NVDA")).toHaveTextContent("-2.50%");
    expect(screen.getByTestId("position-pnl-NVDA")).toHaveClass("text-loss");
  });

  it("explains an empty portfolio", () => {
    render(<PositionsTable positions={[]} onSelect={() => {}} />);
    expect(screen.getByText(/No open positions yet/)).toBeInTheDocument();
  });
});
