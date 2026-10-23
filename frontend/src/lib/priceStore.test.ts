import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FakeEventSource, quote } from "@/test/fixtures";

import { connectPriceStream, MAX_POINTS, PriceStore, toSecondBuckets } from "./priceStore";

function at(ms: number) {
  return new Date(ms).toISOString();
}

describe("PriceStore", () => {
  it("replaces the price map and appends to each ticker's buffer", () => {
    const store = new PriceStore();
    store.applyPrices({ AAPL: quote("AAPL", 190, { timestamp: at(1000) }) });
    store.applyPrices({ AAPL: quote("AAPL", 191, { timestamp: at(1500) }), MSFT: quote("MSFT", 400, { timestamp: at(1500) }) });

    const state = store.getState();
    expect(state.prices.AAPL.price).toBe(191);
    expect(state.history.AAPL).toEqual([
      { time: 1000, price: 190 },
      { time: 1500, price: 191 },
    ]);
    expect(state.history.MSFT).toHaveLength(1);
  });

  it("drops tickers missing from the latest map", () => {
    const store = new PriceStore();
    store.applyPrices({ AAPL: quote("AAPL", 190, { timestamp: at(1000) }), PYPL: quote("PYPL", 60, { timestamp: at(1000) }) });
    store.applyPrices({ AAPL: quote("AAPL", 190.5, { timestamp: at(1500) }) });
    expect(store.getState().prices.PYPL).toBeUndefined();
    expect(store.getState().history.PYPL).toBeUndefined();
  });

  it("ignores a repeated event, e.g. the first one after a reconnect", () => {
    const store = new PriceStore();
    const event = { AAPL: quote("AAPL", 190, { timestamp: at(1000) }) };
    store.applyPrices(event);
    store.applyPrices(event);
    expect(store.getState().history.AAPL).toHaveLength(1);
  });

  it(`caps each buffer at ${MAX_POINTS} points, keeping the newest`, () => {
    const store = new PriceStore();
    for (let i = 0; i < MAX_POINTS + 25; i++) {
      store.applyPrices({ AAPL: quote("AAPL", 100 + i, { timestamp: at(i * 500) }) });
    }
    const buffer = store.getState().history.AAPL;
    expect(buffer).toHaveLength(MAX_POINTS);
    expect(buffer[buffer.length - 1].price).toBe(100 + MAX_POINTS + 24);
    expect(buffer[0].price).toBe(125);
  });

  it("notifies subscribers with a new state object", () => {
    const store = new PriceStore();
    const listener = vi.fn();
    const unsubscribe = store.subscribe(listener);
    const before = store.getState();
    store.applyPrices({ AAPL: quote("AAPL", 190) });
    expect(listener).toHaveBeenCalledTimes(1);
    expect(store.getState()).not.toBe(before);
    unsubscribe();
    store.setStatus("connected");
    expect(listener).toHaveBeenCalledTimes(1);
  });
});

describe("toSecondBuckets", () => {
  it("keeps the last price in each second and returns unix seconds", () => {
    expect(
      toSecondBuckets([
        { time: 1000, price: 1 },
        { time: 1500, price: 2 },
        { time: 2100, price: 3 },
        { time: 4999, price: 4 },
      ]),
    ).toEqual([
      { time: 1, value: 2 },
      { time: 2, value: 3 },
      { time: 4, value: 4 },
    ]);
  });
});

describe("connectPriceStream", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  function connect() {
    const store = new PriceStore();
    const stop = connectPriceStream(store, "/api/stream/prices", {
      createEventSource: (url) => new FakeEventSource(url),
      retryMs: 1000,
    });
    return { store, stop, es: FakeEventSource.latest() };
  }

  it("goes connected on open and applies events", () => {
    const { store, es } = connect();
    expect(es.url).toBe("/api/stream/prices");
    expect(store.getState().status).toBe("reconnecting");
    es.open();
    expect(store.getState().status).toBe("connected");
    es.emit({ AAPL: quote("AAPL", 190) });
    expect(store.getState().prices.AAPL.price).toBe(190);
  });

  it("shows reconnecting while EventSource retries by itself", () => {
    const { store, es } = connect();
    es.open();
    es.fail(0); // CONNECTING
    expect(store.getState().status).toBe("reconnecting");
    es.open();
    expect(store.getState().status).toBe("connected");
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it("shows disconnected when the browser gives up, then opens a new connection", () => {
    const { store, es } = connect();
    es.open();
    es.fail(2); // CLOSED
    expect(store.getState().status).toBe("disconnected");
    expect(es.closed).toBe(true);

    vi.advanceTimersByTime(1000);
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(store.getState().status).toBe("reconnecting");
    FakeEventSource.latest().open();
    expect(store.getState().status).toBe("connected");
  });

  it("ignores malformed events", () => {
    const { store, es } = connect();
    es.onmessage?.(new MessageEvent("message", { data: "not json" }));
    expect(store.getState().prices).toEqual({});
  });

  it("follows the browser going offline and back online", () => {
    const network = new EventTarget();
    const store = new PriceStore();
    connectPriceStream(store, "/api/stream/prices", {
      createEventSource: (url) => new FakeEventSource(url),
      networkEvents: network,
    });
    const first = FakeEventSource.latest();
    first.open();

    network.dispatchEvent(new Event("offline"));
    expect(store.getState().status).toBe("disconnected");
    expect(first.closed).toBe(true);
    // A late event from the closed stream is ignored.
    first.emit({ AAPL: quote("AAPL", 190) });
    expect(store.getState().status).toBe("disconnected");
    expect(store.getState().prices).toEqual({});

    network.dispatchEvent(new Event("online"));
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(store.getState().status).toBe("reconnecting");
    FakeEventSource.latest().open();
    expect(store.getState().status).toBe("connected");
  });

  it("closes the stream and cancels retries when stopped", () => {
    const { stop, es } = connect();
    es.fail(2);
    stop();
    vi.advanceTimersByTime(5000);
    expect(FakeEventSource.instances).toHaveLength(1);
  });
});
