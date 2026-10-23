import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { valuePortfolio } from "@/lib/portfolio";
import { portfolio, position, quote } from "@/test/fixtures";

import { Heatmap } from "./Heatmap";

function rgb(el: HTMLElement): [number, number, number] {
  const m = el.style.backgroundColor.match(/rgb\((\d+), (\d+), (\d+)\)/);
  if (!m) throw new Error(`no rgb background: ${el.style.backgroundColor}`);
  return [Number(m[1]), Number(m[2]), Number(m[3])];
}

describe("Heatmap", () => {
  it("shows an empty state with no positions", () => {
    render(<Heatmap positions={[]} onSelect={() => {}} />);
    expect(screen.getByTestId("heatmap")).toBeInTheDocument();
    expect(screen.getByTestId("heatmap-empty")).toHaveTextContent("No positions yet");
  });

  it("renders a tile per position, colored by the sign of its P&L", () => {
    const v = valuePortfolio(
      portfolio(1000, [position("AAPL", 10, 190, 190), position("MSFT", 5, 400, 400), position("TSLA", 2, 250, 250)]),
      { AAPL: quote("AAPL", 200), MSFT: quote("MSFT", 380), TSLA: quote("TSLA", 250) },
    );
    const onSelect = vi.fn();
    render(<Heatmap positions={v.positions} onSelect={onSelect} />);

    expect(screen.queryByTestId("heatmap-empty")).not.toBeInTheDocument();

    const aapl = screen.getByTestId("heatmap-tile-AAPL");
    expect(aapl).toHaveAttribute("data-pnl-sign", "positive");
    const [ar, ag] = rgb(aapl);
    expect(ag).toBeGreaterThan(ar);

    const msft = screen.getByTestId("heatmap-tile-MSFT");
    expect(msft).toHaveAttribute("data-pnl-sign", "negative");
    const [mr, mg] = rgb(msft);
    expect(mr).toBeGreaterThan(mg);

    const tsla = screen.getByTestId("heatmap-tile-TSLA");
    expect(tsla).toHaveAttribute("data-pnl-sign", "zero");
    expect(tsla.style.backgroundColor).toBe("rgb(58, 65, 84)");

    // Area follows market value: AAPL $2,000 > MSFT $1,900 > TSLA $500.
    const area = (el: HTMLElement) => parseFloat(el.style.width) * parseFloat(el.style.height);
    expect(area(aapl)).toBeGreaterThan(area(msft));
    expect(area(msft)).toBeGreaterThan(area(tsla));

    fireEvent.click(aapl);
    expect(onSelect).toHaveBeenCalledWith("AAPL");
  });
});
