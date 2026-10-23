import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FakeEventSource } from "@/test/fixtures";

import { type CharlaStreamStatus, connectCharlaStream, useCharlaStream } from "./stream";

/** A stand-in for `document` whose visibility the test controls. */
class FakeVisibility extends EventTarget {
  visibilityState: DocumentVisibilityState = "visible";
  set(state: DocumentVisibilityState) {
    this.visibilityState = state;
    this.dispatchEvent(new Event("visibilitychange"));
  }
}

interface Snap {
  v: number;
}

function setup(options: { poll?: () => Promise<Snap> } = {}) {
  const network = new EventTarget();
  const visibility = new FakeVisibility();
  const data: Snap[] = [];
  const statuses: CharlaStreamStatus[] = [];
  const pollErrors: unknown[] = [];
  const stop = connectCharlaStream<Snap>("/api/charla/stream?t=x", (d) => data.push(d), (s) => statuses.push(s), {
    createEventSource: (url) => new FakeEventSource(url),
    retryMs: 1000,
    pollMs: 3000,
    networkEvents: network,
    visibility,
    poll: options.poll,
    onPollError: (e) => pollErrors.push(e),
  });
  const status = () => statuses[statuses.length - 1];
  return { stop, network, visibility, data, statuses, status, pollErrors };
}

describe("connectCharlaStream", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("starts connecting, goes live on open and delivers snapshots", () => {
    const { data, statuses } = setup();
    const es = FakeEventSource.latest();
    expect(es.url).toBe("/api/charla/stream?t=x");
    expect(statuses).toEqual(["connecting"]);
    es.open();
    es.emit({ v: 1 });
    es.emit({ v: 2 });
    expect(statuses).toEqual(["connecting", "live"]);
    expect(data).toEqual([{ v: 1 }, { v: 2 }]);
  });

  it("ignores malformed events", () => {
    const { data } = setup();
    FakeEventSource.latest().onmessage?.(new MessageEvent("message", { data: "{not json" }));
    expect(data).toEqual([]);
  });

  it("shows reconnecting while EventSource retries by itself", () => {
    const { status } = setup();
    const es = FakeEventSource.latest();
    es.open();
    es.fail(0); // CONNECTING
    expect(status()).toBe("reconnecting");
    es.open();
    expect(status()).toBe("live");
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it("goes offline when the browser gives up, then opens a new stream", () => {
    const { status } = setup();
    const first = FakeEventSource.latest();
    first.open();
    first.fail(2); // CLOSED, e.g. a 401 or a dead proxy
    expect(status()).toBe("offline");
    expect(first.closed).toBe(true);

    vi.advanceTimersByTime(999);
    expect(FakeEventSource.instances).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(status()).toBe("reconnecting");
    FakeEventSource.latest().open();
    expect(status()).toBe("live");
  });

  it("follows the browser going offline and back online", () => {
    const { network, status, data } = setup();
    const first = FakeEventSource.latest();
    first.open();

    network.dispatchEvent(new Event("offline"));
    expect(status()).toBe("offline");
    expect(first.closed).toBe(true);
    first.emit({ v: 9 }); // a late event from the closed stream
    expect(data).toEqual([]);

    network.dispatchEvent(new Event("online"));
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(status()).toBe("reconnecting");
    FakeEventSource.latest().open();
    expect(status()).toBe("live");
  });

  it("opens a fresh stream when the page becomes visible again", () => {
    const { visibility, status, data } = setup();
    const first = FakeEventSource.latest();
    first.open();

    visibility.set("hidden");
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(first.closed).toBe(false);

    visibility.set("visible");
    expect(first.closed).toBe(true);
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(status()).toBe("reconnecting");
    first.emit({ v: 1 }); // the old stream is ignored
    expect(data).toEqual([]);

    const second = FakeEventSource.latest();
    second.open();
    second.emit({ v: 2 });
    expect(status()).toBe("live");
    expect(data).toEqual([{ v: 2 }]);
  });

  it("polls every 3 s only while the stream isn't live", async () => {
    let n = 0;
    const poll = vi.fn(async () => ({ v: ++n * 100 }));
    const { data } = setup({ poll });
    const es = FakeEventSource.latest();

    // connecting: polls
    await vi.advanceTimersByTimeAsync(3000);
    expect(poll).toHaveBeenCalledTimes(1);
    expect(data).toEqual([{ v: 100 }]);

    // live: no polls
    es.open();
    await vi.advanceTimersByTimeAsync(9000);
    expect(poll).toHaveBeenCalledTimes(1);

    // reconnecting: polls again
    es.fail(0);
    await vi.advanceTimersByTimeAsync(3000);
    expect(poll).toHaveBeenCalledTimes(2);
    expect(data).toEqual([{ v: 100 }, { v: 200 }]);

    // offline (CLOSED): keeps polling until a new stream goes live
    es.fail(2);
    await vi.advanceTimersByTimeAsync(3000);
    expect(poll).toHaveBeenCalledTimes(3);
    FakeEventSource.latest().open();
    await vi.advanceTimersByTimeAsync(6000);
    expect(poll).toHaveBeenCalledTimes(3);
  });

  it("drops a poll result that lands after the stream came back", async () => {
    let resolve: (s: Snap) => void = () => {};
    const poll = vi.fn(() => new Promise<Snap>((r) => (resolve = r)));
    const { data } = setup({ poll });
    await vi.advanceTimersByTimeAsync(3000);
    expect(poll).toHaveBeenCalledTimes(1);

    const es = FakeEventSource.latest();
    es.open();
    es.emit({ v: 2 });
    resolve({ v: 1 });
    await vi.advanceTimersByTimeAsync(0);
    expect(data).toEqual([{ v: 2 }]);
  });

  it("doesn't stack polls while one is in flight", async () => {
    const poll = vi.fn(() => new Promise<Snap>(() => {}));
    setup({ poll });
    await vi.advanceTimersByTimeAsync(12_000);
    expect(poll).toHaveBeenCalledTimes(1);
  });

  it("reports poll failures and keeps polling", async () => {
    const error = new Error("401");
    const poll = vi.fn().mockRejectedValueOnce(error).mockResolvedValue({ v: 1 });
    const { pollErrors, data } = setup({ poll });
    await vi.advanceTimersByTimeAsync(3000);
    expect(pollErrors).toEqual([error]);
    await vi.advanceTimersByTimeAsync(3000);
    expect(data).toEqual([{ v: 1 }]);
  });

  it("closes everything when stopped", async () => {
    const poll = vi.fn(async () => ({ v: 1 }));
    const { stop, network, visibility } = setup({ poll });
    const es = FakeEventSource.latest();
    es.fail(2);
    stop();
    expect(es.closed).toBe(true);
    await vi.advanceTimersByTimeAsync(10_000);
    network.dispatchEvent(new Event("online"));
    visibility.set("visible");
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(poll).not.toHaveBeenCalled();
  });
});

describe("useCharlaStream", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
  });

  const testOptions = {
    createEventSource: (url: string) => new FakeEventSource(url),
    networkEvents: null,
    visibility: null,
  };

  it("exposes data, status and the receipt time", () => {
    const { result } = renderHook(() => useCharlaStream<Snap>("/s?t=1", undefined, testOptions));
    expect(result.current).toEqual({ data: null, status: "connecting", receivedAt: null, error: null });

    const es = FakeEventSource.latest();
    act(() => {
      es.open();
      es.emit({ v: 7 });
    });
    expect(result.current.status).toBe("live");
    expect(result.current.data).toEqual({ v: 7 });
    expect(typeof result.current.receivedAt).toBe("number");
  });

  it("stays idle without a URL", () => {
    const { result } = renderHook(() => useCharlaStream<Snap>(null, undefined, testOptions));
    expect(result.current).toEqual({ data: null, status: "offline", receivedAt: null, error: null });
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it("reconnects and forgets the old data when the URL changes, and closes on unmount", () => {
    const { result, rerender, unmount } = renderHook(({ url }) => useCharlaStream<Snap>(url, undefined, testOptions), {
      initialProps: { url: "/s?t=1" },
    });
    const first = FakeEventSource.latest();
    act(() => {
      first.open();
      first.emit({ v: 1 });
    });

    rerender({ url: "/s?t=2" });
    expect(first.closed).toBe(true);
    expect(FakeEventSource.latest().url).toBe("/s?t=2");
    expect(result.current.data).toBeNull();
    expect(result.current.status).toBe("connecting");

    unmount();
    expect(FakeEventSource.latest().closed).toBe(true);
  });

  it("doesn't reconnect when only the poll function's identity changes", () => {
    const { rerender } = renderHook(() => useCharlaStream<Snap>("/s?t=1", async () => ({ v: 1 }), testOptions));
    rerender();
    rerender();
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it("uses the latest poll function and surfaces its errors", async () => {
    vi.useFakeTimers();
    try {
      const failing = vi.fn().mockRejectedValue(new Error("Tu sesión expiró."));
      const { result } = renderHook(() => useCharlaStream<Snap>("/s?t=1", failing, { ...testOptions, pollMs: 3000 }));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });
      expect(failing).toHaveBeenCalledTimes(1);
      expect(result.current.error).toEqual(new Error("Tu sesión expiró."));

      failing.mockResolvedValue({ v: 5 });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });
      expect(result.current.data).toEqual({ v: 5 });
      expect(result.current.error).toBeNull();
      expect(result.current.status).toBe("connecting");
    } finally {
      vi.useRealTimers();
    }
  });
});
