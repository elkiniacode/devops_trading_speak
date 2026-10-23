"use client";

import { useEffect, useRef, useState } from "react";

import type { EventSourceLike } from "@/lib/priceStore";

export type CharlaStreamStatus = "connecting" | "live" | "reconnecting" | "offline";

export interface CharlaStreamOptions<T> {
  /** Fallback fetch (e.g. `() => charlaApi.me(token)`), run every `pollMs` while the stream isn't live. */
  poll?: () => Promise<T>;
  /** Called with each failed poll's error (an ApiError, e.g. 401). */
  onPollError?: (error: unknown) => void;
  pollMs?: number;
  /** Delay before reopening after the browser gives up (readyState CLOSED). */
  retryMs?: number;
  /** Tests pass a fake. */
  createEventSource?: (url: string) => EventSourceLike;
  /** Source of "offline" / "online"; `window` by default, null for none. */
  networkEvents?: EventTarget | null;
  /** Source of "visibilitychange" and `visibilityState`; `document` by default, null for none. */
  visibility?: Pick<Document, "visibilityState" | "addEventListener" | "removeEventListener"> | null;
}

const EVENT_SOURCE_CLOSED = 2;

/**
 * Follow an SSE endpoint that sends whole JSON snapshots. Modelled on connectPriceStream:
 * - EventSource retries by itself while CONNECTING ("reconnecting"); if it gives up (CLOSED,
 *   e.g. a 401 or a dead proxy) we report "offline" and open a new one after `retryMs`.
 * - offline closes the stream; online reopens it at once.
 * - Phones kill background connections without telling the page, so coming back to the
 *   tab (visibilitychange -> visible) always opens a fresh stream, which starts with a snapshot.
 * - While not live, an optional `poll` keeps the data fresh every `pollMs`.
 *
 * Returns a function that closes everything for good.
 */
export function connectCharlaStream<T>(
  url: string,
  onData: (data: T) => void,
  onStatus: (status: CharlaStreamStatus) => void,
  options: CharlaStreamOptions<T> = {},
): () => void {
  const create = options.createEventSource ?? ((u: string) => new EventSource(u) as EventSourceLike);
  const retryMs = options.retryMs ?? 3000;
  const pollMs = options.pollMs ?? 3000;
  const network = options.networkEvents !== undefined ? options.networkEvents : typeof window !== "undefined" ? window : null;
  const visibility = options.visibility !== undefined ? options.visibility : typeof document !== "undefined" ? document : null;
  const { poll, onPollError } = options;

  let source: EventSourceLike | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | undefined;
  let pollTimer: ReturnType<typeof setInterval> | undefined;
  let polling = false;
  let stopped = false;
  let status: CharlaStreamStatus | null = null;

  const setStatus = (next: CharlaStreamStatus) => {
    if (next === status) return;
    status = next;
    onStatus(next);
  };

  const close = () => {
    clearTimeout(retryTimer);
    retryTimer = undefined;
    source?.close();
    source = null;
  };

  const open = () => {
    if (stopped) return;
    close();
    setStatus(status === null ? "connecting" : "reconnecting");
    const es = create(url);
    source = es;
    es.onopen = () => {
      if (source === es) setStatus("live");
    };
    es.onmessage = (event) => {
      if (source !== es) return;
      let data: T;
      try {
        data = JSON.parse(event.data as string) as T;
      } catch {
        return; // a malformed event; the next snapshot replaces it anyway
      }
      setStatus("live");
      onData(data);
    };
    es.onerror = () => {
      if (source !== es) return;
      if (es.readyState === EVENT_SOURCE_CLOSED) {
        close();
        setStatus("offline");
        retryTimer = setTimeout(open, retryMs);
      } else {
        setStatus("reconnecting");
      }
    };
  };

  const onOffline = () => {
    close();
    setStatus("offline");
  };

  const onVisibility = () => {
    if (visibility?.visibilityState === "visible") open();
  };

  const tick = () => {
    if (stopped || status === "live" || polling || !poll) return;
    polling = true;
    poll()
      .then(
        (data) => {
          // A stream that came back meanwhile has fresher data.
          if (!stopped && status !== "live") onData(data);
        },
        (error: unknown) => {
          if (!stopped) onPollError?.(error);
        },
      )
      .finally(() => {
        polling = false;
      });
  };

  network?.addEventListener("offline", onOffline);
  network?.addEventListener("online", open);
  visibility?.addEventListener("visibilitychange", onVisibility);
  if (poll) pollTimer = setInterval(tick, pollMs);
  open();

  return () => {
    stopped = true;
    network?.removeEventListener("offline", onOffline);
    network?.removeEventListener("online", open);
    visibility?.removeEventListener("visibilitychange", onVisibility);
    clearInterval(pollTimer);
    close();
  };
}

export interface CharlaStreamState<T> {
  data: T | null;
  status: CharlaStreamStatus;
  /** performance.now() when `data` arrived (stream or poll), for local countdowns. */
  receivedAt: number | null;
  /** The last poll error, cleared by the next data. */
  error: unknown;
}

export type UseCharlaStreamOptions = Omit<CharlaStreamOptions<unknown>, "poll" | "onPollError">;

const INITIAL: CharlaStreamState<never> = { data: null, status: "connecting", receivedAt: null, error: null };
const NO_URL: CharlaStreamState<never> = { data: null, status: "offline", receivedAt: null, error: null };

/**
 * React binding for connectCharlaStream. A null `url` (no token or key yet) stays idle.
 * `poll` may be a new function every render; only `url` and whether a poll exists matter.
 */
export function useCharlaStream<T>(
  url: string | null,
  poll?: () => Promise<T>,
  options?: UseCharlaStreamOptions,
): CharlaStreamState<T> {
  const [state, setState] = useState<CharlaStreamState<T>>(url ? INITIAL : NO_URL);
  const pollRef = useRef(poll);
  const optionsRef = useRef(options);
  useEffect(() => {
    pollRef.current = poll;
    optionsRef.current = options;
  });
  const hasPoll = poll !== undefined;

  useEffect(() => {
    if (!url) {
      setState(NO_URL);
      return;
    }
    setState(INITIAL);
    return connectCharlaStream<T>(
      url,
      (data) => setState((s) => ({ ...s, data, receivedAt: performance.now(), error: null })),
      (status) => setState((s) => (s.status === status ? s : { ...s, status })),
      {
        ...optionsRef.current,
        poll: hasPoll ? () => (pollRef.current as () => Promise<T>)() : undefined,
        onPollError: (error) => setState((s) => ({ ...s, error })),
      },
    );
  }, [url, hasPoll]);

  return state;
}
