import type { Portfolio, Position, PriceUpdate, WatchlistItem } from "@/lib/types";

export function quote(ticker: string, price: number, overrides: Partial<PriceUpdate> = {}): PriceUpdate {
  const reference = overrides.reference_price ?? price;
  const previous = overrides.previous_price ?? price;
  const change = price - reference;
  return {
    ticker,
    price,
    previous_price: previous,
    reference_price: reference,
    change,
    change_percent: reference ? (change / reference) * 100 : 0,
    direction: price > previous ? "up" : price < previous ? "down" : "flat",
    timestamp: "2026-10-19T14:03:12.500Z",
    ...overrides,
  };
}

export function position(ticker: string, quantity: number, avg_cost: number, current_price: number | null): Position {
  return {
    ticker,
    quantity,
    avg_cost,
    current_price,
    market_value: current_price === null ? null : quantity * current_price,
    unrealized_pnl: current_price === null ? null : (current_price - avg_cost) * quantity,
    unrealized_pnl_percent: current_price === null ? null : ((current_price - avg_cost) / avg_cost) * 100,
    stale: false,
  };
}

export function portfolio(cash: number, positions: Position[]): Portfolio {
  const positions_value = positions.reduce((s, p) => s + (p.market_value ?? p.quantity * p.avg_cost), 0);
  const total_value = cash + positions_value;
  return {
    cash_balance: cash,
    positions,
    positions_value,
    total_value,
    total_pnl: total_value - 10000,
    total_pnl_percent: ((total_value - 10000) / 10000) * 100,
    valuation_complete: positions.every((p) => p.current_price !== null),
    as_of: "2026-10-19T14:03:12.500Z",
  };
}

export function watchItem(ticker: string, price: number | null): WatchlistItem {
  return {
    ticker,
    added_at: "2026-10-19T14:00:00.000Z",
    quote: price === null ? null : quote(ticker, price),
  };
}

/** A controllable stand-in for the browser's EventSource. */
export class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readyState = 0;
  onopen: ((ev: Event) => unknown) | null = null;
  onmessage: ((ev: MessageEvent) => unknown) | null = null;
  onerror: ((ev: Event) => unknown) | null = null;
  closed = false;

  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }

  open() {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }

  emit(data: unknown) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(data) }));
  }

  fail(readyState: 0 | 2) {
    this.readyState = readyState;
    this.onerror?.(new Event("error"));
  }

  close() {
    this.closed = true;
    this.readyState = 2;
  }

  static latest(): FakeEventSource {
    return FakeEventSource.instances[FakeEventSource.instances.length - 1];
  }
}
