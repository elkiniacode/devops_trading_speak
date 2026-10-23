import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PriceProvider, usePrices } from "@/state/prices";
import { FakeEventSource } from "@/test/fixtures";

import { ConnectionStatus } from "./ConnectionStatus";

function LiveStatus() {
  return <ConnectionStatus status={usePrices().status} />;
}

describe("ConnectionStatus", () => {
  it.each([
    ["connected", "Live"],
    ["reconnecting", "Reconnecting"],
    ["disconnected", "Offline"],
  ] as const)("renders %s", (status, label) => {
    render(<ConnectionStatus status={status} />);
    const el = screen.getByTestId("connection-status");
    expect(el).toHaveAttribute("data-status", status);
    expect(el).toHaveTextContent(label);
  });
});

describe("connection indicator driven by EventSource (S9)", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("follows onopen and onerror", () => {
    vi.useFakeTimers();
    render(
      <PriceProvider>
        <LiveStatus />
      </PriceProvider>,
    );
    const el = screen.getByTestId("connection-status");
    expect(el).toHaveAttribute("data-status", "reconnecting");

    const es = FakeEventSource.latest();
    expect(es.url).toBe("/api/stream/prices");
    act(() => es.open());
    expect(el).toHaveAttribute("data-status", "connected");

    act(() => es.fail(0)); // the browser is retrying
    expect(el).toHaveAttribute("data-status", "reconnecting");

    act(() => es.open());
    expect(el).toHaveAttribute("data-status", "connected");

    act(() => es.fail(2)); // the browser gave up
    expect(el).toHaveAttribute("data-status", "disconnected");

    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(FakeEventSource.instances).toHaveLength(2);
    act(() => FakeEventSource.latest().open());
    expect(el).toHaveAttribute("data-status", "connected");
  });

  it("closes the stream on unmount", () => {
    const { unmount } = render(
      <PriceProvider>
        <LiveStatus />
      </PriceProvider>,
    );
    const es = FakeEventSource.latest();
    unmount();
    expect(es.closed).toBe(true);
  });
});
