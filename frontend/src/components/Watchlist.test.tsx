import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { quote, watchItem } from "@/test/fixtures";

import { Watchlist, WatchlistRow } from "./Watchlist";

function renderWatchlist(overrides: Partial<Parameters<typeof Watchlist>[0]> = {}) {
  const props = {
    items: [watchItem("AAPL", 190), watchItem("MSFT", 400)],
    prices: { AAPL: quote("AAPL", 191.5, { reference_price: 190, previous_price: 191 }) },
    history: {
      AAPL: [
        { time: 1, price: 190 },
        { time: 2, price: 191 },
        { time: 3, price: 191.5 },
      ],
    },
    selectedTicker: "AAPL",
    mode: "simulator" as const,
    onSelect: vi.fn(),
    onAdd: vi.fn().mockResolvedValue(null),
    onRemove: vi.fn().mockResolvedValue(null),
    ...overrides,
  };
  render(<Watchlist {...props} />);
  return props;
}

describe("Watchlist", () => {
  it("renders a row per ticker with live price, change and sparkline", () => {
    renderWatchlist();
    expect(screen.getByTestId("watchlist")).toBeInTheDocument();
    expect(screen.getByTestId("watchlist-row-AAPL")).toHaveAttribute("data-direction", "up");
    expect(screen.getByTestId("watchlist-price-AAPL")).toHaveTextContent("191.50");
    expect(screen.getByTestId("watchlist-change-AAPL")).toHaveTextContent("+0.79%");
    expect(screen.getByTestId("watchlist-change-AAPL")).toHaveAttribute("title", "Change since session start");
    expect(screen.getByTestId("sparkline-AAPL")).toHaveAttribute("data-points", "3");
    // MSFT has no SSE price yet: falls back to the REST quote and an empty sparkline.
    expect(screen.getByTestId("watchlist-price-MSFT")).toHaveTextContent("400.00");
    expect(screen.getByTestId("sparkline-MSFT")).toHaveAttribute("data-points", "0");
  });

  it("selects a ticker when its row is clicked", () => {
    const props = renderWatchlist();
    fireEvent.click(screen.getByRole("button", { name: "Select MSFT" }));
    expect(props.onSelect).toHaveBeenCalledWith("MSFT");
  });

  it("removes a ticker", async () => {
    const props = renderWatchlist();
    fireEvent.click(screen.getByTestId("watchlist-remove-MSFT"));
    await waitFor(() => expect(props.onRemove).toHaveBeenCalledWith("MSFT"));
  });

  it("adds an upper-cased ticker and clears the input", async () => {
    const props = renderWatchlist();
    const input = screen.getByTestId("watchlist-add-input");
    fireEvent.change(input, { target: { value: "pypl" } });
    fireEvent.click(screen.getByTestId("watchlist-add-button"));
    await waitFor(() => expect(props.onAdd).toHaveBeenCalledWith("PYPL"));
    await waitFor(() => expect(input).toHaveValue(""));
    expect(screen.queryByTestId("watchlist-error")).not.toBeInTheDocument();
  });

  it("shows the server's error when adding fails", async () => {
    renderWatchlist({ onAdd: vi.fn().mockResolvedValue("Unknown ticker: XYZQ") });
    fireEvent.change(screen.getByTestId("watchlist-add-input"), { target: { value: "XYZQ" } });
    fireEvent.click(screen.getByTestId("watchlist-add-button"));
    expect(await screen.findByTestId("watchlist-error")).toHaveTextContent("Unknown ticker: XYZQ");
    expect(screen.getByTestId("watchlist-add-input")).toHaveValue("XYZQ");
  });
});

describe("steady watchlist prices", () => {
  function row(price: number) {
    return (
      <ul>
        <WatchlistRow
          ticker="AAPL"
          quote={quote("AAPL", price)}
          points={[]}
          selected={false}
          changeHint=""
          onSelect={() => {}}
          onRemove={() => {}}
        />
      </ul>
    );
  }

  it("keeps price values free of flash and glow classes as quotes change", () => {
    const { rerender } = render(row(190));
    const cell = screen.getByTestId("watchlist-price-AAPL");
    expect(cell).toHaveTextContent("190.00");
    expect(cell.className).not.toMatch(/flash|price-cell/);
    rerender(row(190.5));
    expect(cell).toHaveTextContent("190.50");
    expect(cell.className).not.toMatch(/flash|price-cell/);
    expect(cell).not.toHaveClass("flash-up");
    expect(cell).not.toHaveClass("flash-down");
  });
});
