import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "./api";

function respond(status: number, body: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

describe("api", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("sends JSON bodies and returns the parsed response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(respond(200, { watchlist: [] }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api.addToWatchlist("PYPL")).resolves.toEqual({ watchlist: [] });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/watchlist");
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"ticker":"PYPL"}');
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
  });

  it("surfaces FastAPI's detail string", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(respond(400, { detail: "Unknown ticker: XYZQ" })));
    await expect(api.trade("XYZQ", 1, "buy")).rejects.toMatchObject({ status: 400, detail: "Unknown ticker: XYZQ" });
  });

  it("reads the first message of a 422 validation list", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(respond(422, { detail: [{ loc: ["body", "quantity"], msg: "Input should be a valid number" }] })),
    );
    await expect(api.trade("AAPL", Number.NaN, "buy")).rejects.toMatchObject({ detail: "Input should be a valid number" });
  });

  it("explains an unreachable server", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const err = await api.portfolio().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).detail).toMatch(/Can't reach the FinAlly server/);
  });

  it("gives up on a chat reply after 45 seconds", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
          }),
      ),
    );
    let settled = false;
    const pending = api.chat("hello").catch((e: unknown) => e).finally(() => (settled = true));
    await vi.advanceTimersByTimeAsync(44_000);
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(1_000);
    const err = await pending;
    expect((err as ApiError).detail).toBe("The server took too long to respond. Try again.");
  });
});
