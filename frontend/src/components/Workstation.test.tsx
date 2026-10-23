import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Portfolio } from "@/lib/types";
import { FakeEventSource, portfolio, position, quote, watchItem } from "@/test/fixtures";

vi.mock("lightweight-charts", () => {
  const series = { setData: vi.fn(), update: vi.fn(), createPriceLine: vi.fn(() => ({})), removePriceLine: vi.fn() };
  return {
    createChart: vi.fn(() => ({
      addSeries: vi.fn(() => series),
      timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
      remove: vi.fn(),
    })),
    CandlestickSeries: "Candlestick",
    LineSeries: "Line",
    HistogramSeries: "Histogram",
    AreaSeries: "Area",
    BaselineSeries: "Baseline",
    ColorType: { Solid: "solid" },
    CrosshairMode: { Magnet: 1 },
    LineStyle: { Dashed: 2 },
  };
});

const { Workstation } = await import("./Workstation");

interface Call {
  method: string;
  path: string;
  body: unknown;
}

/** A tiny in-memory backend speaking the CONTRACTS.md §5 shapes. */
function fakeBackend() {
  const calls: Call[] = [];
  let state: Portfolio = portfolio(10000, []);
  let watchlist = [watchItem("AAPL", 190), watchItem("MSFT", 400)];

  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const path = url.split("?")[0];
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ method, path, body });
    const ok = (data: unknown) => ({ ok: true, status: 200, json: async () => data });
    const fail = (status: number, detail: string) => ({ ok: false, status, json: async () => ({ detail }) });

    if (path === "/api/health") return ok({ status: "ok", market_data: "simulator", llm: "mock" });
    if (path === "/api/portfolio") return ok(state);
    if (path === "/api/portfolio/history") return ok({ snapshots: [{ total_value: 10000, recorded_at: "2026-10-19T14:00:00.000Z" }] });
    if (path === "/api/workstation") return ok({ orders: [], trades: [], activity: [], risk: [] });
    if (path === "/api/market/candles") return ok({ ticker: "AAPL", timeframe: "H1", candles: [], synthetic: true });
    if (path === "/api/chat/history") return ok({ messages: [] });
    if (path === "/api/watchlist" && method === "GET") return ok({ watchlist });
    if (path.startsWith("/api/watchlist/") && method === "DELETE") {
      const ticker = decodeURIComponent(path.split("/").pop()!);
      watchlist = watchlist.filter((w) => w.ticker !== ticker);
      return ok({ watchlist });
    }
    if (path === "/api/portfolio/trade") {
      const { ticker, quantity, side } = body as { ticker: string; quantity: number; side: string };
      if (side === "sell") return fail(400, `Insufficient shares: you have 0 ${ticker}, tried to sell ${quantity}`);
      state = portfolio(state.cash_balance - quantity * 400, [position(ticker, quantity, 400, 400)]);
      const trade = { id: "t1", ticker, side, quantity, price: 400, total: quantity * 400, executed_at: "2026-10-19T14:03:12.900Z" };
      return ok({ trade, portfolio: state });
    }
    if (path === "/api/orders" && method === "POST") {
      const { ticker, notional, side } = body as { ticker: string; notional: number; side: string };
      if (side === "sell") return fail(400, `Insufficient shares: you have 0 ${ticker}`);
      const quantity = notional / 400;
      state = portfolio(state.cash_balance - notional, [position(ticker, quantity, 400, 400)]);
      return ok({ status: "filled", trade: { id: "t2", ticker, side, quantity, price: 400, total: notional, executed_at: "2026-10-19T14:03:12.900Z" }, portfolio: state });
    }
    return fail(404, "Not Found");
  });

  const count = (path: string, method = "GET") => calls.filter((c) => c.path === path && c.method === method).length;
  return { fetchMock, calls, count };
}

describe("Workstation", () => {
  let backend: ReturnType<typeof fakeBackend>;

  beforeEach(() => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1440 });
    backend = fakeBackend();
    FakeEventSource.instances = [];
    vi.stubGlobal("fetch", backend.fetchMock);
    vi.stubGlobal("EventSource", FakeEventSource);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  async function renderLoaded() {
    render(<Workstation />);
    await waitFor(() => expect(screen.getByTestId("header-total-value")).toHaveTextContent("$10,000.00"));
    act(() => {
      const es = FakeEventSource.latest();
      es.open();
      es.emit({ AAPL: quote("AAPL", 190), MSFT: quote("MSFT", 400) });
    });
  }

  it("loads the initial state and streams prices", async () => {
    await renderLoaded();
    expect(screen.getByTestId("header-cash")).toHaveTextContent("$10,000.00");
    expect(screen.getByTestId("connection-status")).toHaveAttribute("data-status", "connected");
    expect(screen.getByTestId("market-mode")).toHaveTextContent("SIM");
    expect(screen.getByTestId("watchlist-price-AAPL")).toHaveTextContent("190.00");
    expect(screen.getByTestId("main-chart")).toHaveAttribute("data-ticker", "AAPL");
    expect(screen.getByTestId("heatmap-empty")).toBeInTheDocument();
    expect(screen.getByTestId("pnl-chart")).toHaveAttribute("data-points", "1");
    expect(FakeEventSource.latest().url).toBe("/api/stream/prices");
  });

  it("selects a ticker and submits a market order", async () => {
    await renderLoaded();
    fireEvent.click(screen.getByRole("button", { name: "Select MSFT" }));
    expect(screen.getByTestId("main-chart")).toHaveAttribute("data-ticker", "MSFT");
    expect(screen.getByRole("region", { name: "Trade" })).toHaveTextContent("MSFT");

    const before = {
      portfolio: backend.count("/api/portfolio"),
      watchlist: backend.count("/api/watchlist"),
      history: backend.count("/api/portfolio/history"),
    };
    fireEvent.change(screen.getByRole("spinbutton", { name: /AMOUNT/ }), { target: { value: "800" } });
    fireEvent.click(screen.getByRole("button", { name: "BUY MSFT" }));

    expect(await screen.findByText("ORDER FILLED")).toBeInTheDocument();
    expect(backend.calls.find((c) => c.path === "/api/orders" && c.method === "POST")?.body).toEqual(expect.objectContaining({ ticker: "MSFT", notional: 800, side: "buy", type: "market" }));
    expect(screen.getByTestId("header-cash")).toHaveTextContent("$9,200.00");
    expect(screen.getByTestId("position-qty-MSFT")).toHaveTextContent("2");
    expect(screen.getByTestId("heatmap-tile-MSFT")).toBeInTheDocument();

    // CONTRACTS R29: portfolio, watchlist and history are refetched after a trade.
    await waitFor(() => {
      expect(backend.count("/api/portfolio")).toBeGreaterThan(before.portfolio);
      expect(backend.count("/api/watchlist")).toBeGreaterThan(before.watchlist);
      expect(backend.count("/api/portfolio/history")).toBeGreaterThan(before.history);
    });
  });

  it("shows a rejected order inline without refetching", async () => {
    await renderLoaded();
    const before = backend.count("/api/portfolio");
    fireEvent.click(screen.getByRole("button", { name: /^SELL$/ }));
    fireEvent.click(screen.getByRole("button", { name: "SELL AAPL" }));
    const message = await screen.findByRole("alert");
    expect(message).toHaveTextContent("Insufficient shares: you have 0 AAPL");
    expect(backend.count("/api/portfolio")).toBe(before);
  });

  it("removes a ticker from the watchlist", async () => {
    await renderLoaded();
    fireEvent.click(screen.getByTestId("watchlist-remove-MSFT"));
    await waitFor(() => expect(screen.queryByTestId("watchlist-row-MSFT")).not.toBeInTheDocument());
    expect(backend.count("/api/watchlist/MSFT", "DELETE")).toBe(1);
  });

  it("refetches everything when the price stream reconnects", async () => {
    await renderLoaded();
    const before = backend.count("/api/portfolio");
    act(() => FakeEventSource.latest().fail(0));
    expect(screen.getByTestId("connection-status")).toHaveAttribute("data-status", "reconnecting");
    act(() => FakeEventSource.latest().open());
    await waitFor(() => expect(backend.count("/api/portfolio")).toBe(before + 1));
  });

  it("toggles the assistant panel", async () => {
    await renderLoaded();
    expect(screen.getByTestId("chat-panel")).toBeVisible();
    fireEvent.click(screen.getByTestId("chat-toggle"));
    expect(screen.queryByTestId("chat-panel")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Trade" })).toBeVisible();
    fireEvent.click(screen.getByTestId("chat-toggle"));
    expect(screen.getByTestId("chat-panel")).toBeVisible();
  });
});
