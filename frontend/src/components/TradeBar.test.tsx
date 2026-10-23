import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Trade } from "@/lib/types";
import { quote } from "@/test/fixtures";

import { TradeBar } from "./TradeBar";

const trade: Trade = {
  id: "t1",
  ticker: "AAPL",
  side: "buy",
  quantity: 10,
  price: 190.12,
  total: 1901.2,
  executed_at: "2026-10-19T14:03:12.900Z",
};

function renderBar(overrides: Partial<Parameters<typeof TradeBar>[0]> = {}) {
  const props = {
    selection: null,
    prices: { AAPL: quote("AAPL", 190.12) },
    holdings: {},
    onTrade: vi.fn().mockResolvedValue({ ok: true, trade }),
    ...overrides,
  };
  const view = render(<TradeBar {...props} />);
  return { props, ...view };
}

describe("TradeBar", () => {
  it("pre-fills the ticker when a watchlist row is clicked, not for the default selection", () => {
    const { props, rerender } = renderBar({ selection: { ticker: "AAPL", seq: 0 } });
    expect(screen.getByTestId("trade-ticker-input")).toHaveValue("");
    rerender(<TradeBar {...props} selection={{ ticker: "MSFT", seq: 1 }} />);
    expect(screen.getByTestId("trade-ticker-input")).toHaveValue("MSFT");
  });

  it("buys and reports the fill inline", async () => {
    const { props } = renderBar();
    fireEvent.change(screen.getByTestId("trade-ticker-input"), { target: { value: "aapl" } });
    fireEvent.change(screen.getByTestId("trade-quantity-input"), { target: { value: "10" } });
    expect(screen.getByText("Est. $1,901.20")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("trade-buy-button"));

    expect(props.onTrade).toHaveBeenCalledWith("AAPL", 10, "buy");
    const message = await screen.findByTestId("trade-message");
    expect(message).toHaveAttribute("data-status", "success");
    expect(message).toHaveTextContent("Bought 10 AAPL at $190.12 ($1,901.20)");
  });

  it("accepts fractional quantities and sells", async () => {
    const { props } = renderBar({ holdings: { AAPL: 2 } });
    fireEvent.change(screen.getByTestId("trade-ticker-input"), { target: { value: "AAPL" } });
    fireEvent.change(screen.getByTestId("trade-quantity-input"), { target: { value: "0.5" } });
    expect(screen.getByText("Holding 2")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("trade-sell-button"));
    await waitFor(() => expect(props.onTrade).toHaveBeenCalledWith("AAPL", 0.5, "sell"));
  });

  it("shows the server's rejection as an error", async () => {
    renderBar({ onTrade: vi.fn().mockResolvedValue({ ok: false, error: "Insufficient cash: need $1,901.20, have $500.00" }) });
    fireEvent.change(screen.getByTestId("trade-ticker-input"), { target: { value: "AAPL" } });
    fireEvent.change(screen.getByTestId("trade-quantity-input"), { target: { value: "10" } });
    fireEvent.click(screen.getByTestId("trade-buy-button"));
    const message = await screen.findByTestId("trade-message");
    expect(message).toHaveAttribute("data-status", "error");
    expect(message).toHaveTextContent("Insufficient cash");
  });

  it("validates before calling the server", () => {
    const { props } = renderBar();
    fireEvent.click(screen.getByTestId("trade-buy-button"));
    expect(screen.getByTestId("trade-message")).toHaveTextContent("Enter a ticker symbol.");
    fireEvent.change(screen.getByTestId("trade-ticker-input"), { target: { value: "AAPL" } });
    fireEvent.click(screen.getByTestId("trade-buy-button"));
    expect(screen.getByTestId("trade-message")).toHaveTextContent("Enter a quantity greater than 0.");
    expect(props.onTrade).not.toHaveBeenCalled();
  });
});
