import type { PriceMap } from "./types";

export type ConnectionStatus = "connected" | "reconnecting" | "disconnected";

/** One price observation; `time` is unix milliseconds from the server's timestamp. */
export interface PricePoint {
  time: number;
  price: number;
}

/** Per-ticker buffer cap, shared by the sparklines and the main chart (CONTRACTS R28). */
export const MAX_POINTS = 1000;

export interface PriceState {
  prices: PriceMap;
  history: Record<string, PricePoint[]>;
  status: ConnectionStatus;
}

const EMPTY_STATE: PriceState = { prices: {}, history: {}, status: "reconnecting" };

/**
 * Holds the latest SSE price map, a rolling per-ticker price buffer accumulated since
 * page load, and the stream's connection status. Every change produces a new immutable
 * state object, so it plugs straight into React's useSyncExternalStore.
 */
export class PriceStore {
  private state: PriceState = EMPTY_STATE;
  private listeners = new Set<() => void>();

  getState = (): PriceState => this.state;

  /** The server render (static export) never sees prices. */
  getServerState = (): PriceState => EMPTY_STATE;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  /**
   * Apply one SSE event. The map holds every tracked ticker, so tickers missing from it
   * are dropped along with their buffers (MARKET_INTERFACE.md §9).
   */
  applyPrices(prices: PriceMap): void {
    const history: Record<string, PricePoint[]> = {};
    for (const [ticker, update] of Object.entries(prices)) {
      const buffer = this.state.history[ticker] ?? [];
      const time = Date.parse(update.timestamp);
      const last = buffer[buffer.length - 1];
      if (Number.isNaN(time) || (last && last.time >= time)) {
        // A repeated event (e.g. the first one after a reconnect) adds nothing new.
        history[ticker] = buffer;
        continue;
      }
      const next = buffer.length >= MAX_POINTS ? buffer.slice(buffer.length - MAX_POINTS + 1) : buffer.slice();
      next.push({ time, price: update.price });
      history[ticker] = next;
    }
    this.setState({ ...this.state, prices, history });
  }

  setStatus(status: ConnectionStatus): void {
    if (status !== this.state.status) this.setState({ ...this.state, status });
  }

  private setState(next: PriceState): void {
    this.state = next;
    for (const listener of this.listeners) listener();
  }
}

/** The subset of EventSource the stream needs; tests pass a fake. */
export interface EventSourceLike {
  readonly readyState: number;
  onopen: ((ev: Event) => unknown) | null;
  onmessage: ((ev: MessageEvent) => unknown) | null;
  onerror: ((ev: Event) => unknown) | null;
  close(): void;
}

const EVENT_SOURCE_CLOSED = 2;

export interface StreamOptions {
  createEventSource?: (url: string) => EventSourceLike;
  /** Delay before reopening after the browser gives up (readyState CLOSED). */
  retryMs?: number;
  /** Source of the browser's "offline" / "online" events; `window` by default, null for none. */
  networkEvents?: EventTarget | null;
}

/**
 * Connect the store to the SSE endpoint. EventSource retries on its own while it is
 * CONNECTING ("reconnecting"); if the browser gives up (CLOSED, e.g. a non-SSE error
 * response) we report "disconnected" and open a new connection after `retryMs`.
 *
 * An already-open stream can keep flowing after the browser goes offline, so we also
 * follow the window's offline/online events: offline closes the stream ("disconnected"),
 * online reconnects at once.
 *
 * Returns a function that closes the stream for good.
 */
export function connectPriceStream(store: PriceStore, url: string, options: StreamOptions = {}): () => void {
  const create = options.createEventSource ?? ((u: string) => new EventSource(u) as EventSourceLike);
  const retryMs = options.retryMs ?? 3000;
  const network = options.networkEvents !== undefined ? options.networkEvents : typeof window !== "undefined" ? window : null;
  let source: EventSourceLike | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | undefined;
  let stopped = false;

  const close = () => {
    clearTimeout(retryTimer);
    source?.close();
    source = null;
  };

  const open = () => {
    if (stopped) return;
    close();
    store.setStatus("reconnecting");
    const es = create(url);
    source = es;
    es.onopen = () => {
      if (source === es) store.setStatus("connected");
    };
    es.onmessage = (event) => {
      if (source !== es) return;
      let prices: PriceMap;
      try {
        prices = JSON.parse(event.data as string) as PriceMap;
      } catch {
        return; // ignore a malformed event; the next one replaces the whole map anyway
      }
      store.setStatus("connected");
      store.applyPrices(prices);
    };
    es.onerror = () => {
      if (source !== es) return;
      if (es.readyState === EVENT_SOURCE_CLOSED) {
        close();
        store.setStatus("disconnected");
        retryTimer = setTimeout(open, retryMs);
      } else {
        store.setStatus("reconnecting");
      }
    };
  };

  const onOffline = () => {
    close();
    store.setStatus("disconnected");
  };

  network?.addEventListener("offline", onOffline);
  network?.addEventListener("online", open);
  open();
  return () => {
    stopped = true;
    network?.removeEventListener("offline", onOffline);
    network?.removeEventListener("online", open);
    close();
  };
}

/**
 * Collapse a price buffer into 1-second buckets (last price wins) for Lightweight Charts,
 * which needs strictly increasing times and doesn't do sub-second steps (PLAN R28).
 * Returns times in unix seconds.
 */
export function toSecondBuckets(points: PricePoint[]): { time: number; value: number }[] {
  const out: { time: number; value: number }[] = [];
  for (const point of points) {
    const second = Math.floor(point.time / 1000);
    const last = out[out.length - 1];
    if (last && last.time === second) last.value = point.price;
    else if (!last || second > last.time) out.push({ time: second, value: point.price });
  }
  return out;
}
