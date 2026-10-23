import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { valuePortfolio } from "@/lib/portfolio";
import { portfolio, position, quote } from "@/test/fixtures";

import { Header } from "./Header";

describe("Header", () => {
  it("shows the live total, cash, P&L and market mode", () => {
    const v = valuePortfolio(portfolio(8098.8, [position("AAPL", 10, 190.12, 190.12)]), {
      AAPL: quote("AAPL", 191.2),
    });
    render(<Header valuation={v} status="connected" mode="simulator" chatOpen onToggleChat={() => {}} />);

    expect(screen.getByTestId("header-total-value")).toHaveTextContent("$10,010.80");
    expect(screen.getByTestId("header-cash")).toHaveTextContent("$8,098.80");
    expect(screen.getByTestId("header-pnl")).toHaveTextContent("+$10.80 (+0.11%)");
    expect(screen.getByTestId("market-mode")).toHaveTextContent("SIM");
    expect(screen.getByTestId("connection-status")).toHaveAttribute("data-status", "connected");
  });

  it.each([
    ["massive-snapshot", "DELAYED"],
    ["massive-eod", "EOD"],
  ] as const)("labels %s as %s", (mode, label) => {
    render(<Header valuation={null} status="reconnecting" mode={mode} chatOpen={false} onToggleChat={() => {}} />);
    expect(screen.getByTestId("market-mode")).toHaveTextContent(label);
    expect(screen.getByTestId("header-total-value")).toHaveTextContent("—");
  });

  it("toggles the chat panel", () => {
    const onToggle = vi.fn();
    render(<Header valuation={null} status="connected" mode={null} chatOpen={false} onToggleChat={onToggle} />);
    const toggle = screen.getByTestId("chat-toggle");
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(toggle);
    expect(onToggle).toHaveBeenCalled();
  });
});
