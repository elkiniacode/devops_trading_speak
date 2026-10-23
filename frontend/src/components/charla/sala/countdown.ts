import { useEffect, useState } from "react";

import { remainingMs } from "@/lib/charla/format";
import type { RoomState } from "@/lib/charla/types";

/** Under this many ms left, the timer turns red. */
export const WARN_MS = 5000;

export interface Countdown {
  /** Milliseconds left, never negative; 0 when no question is open. */
  ms: number;
  /** Whole seconds on screen, rounded up so 0 means time is out. */
  seconds: number;
  /** Share of the question's time still left, 0..100. */
  pct: number;
  warn: boolean;
}

type Timing = Pick<RoomState, "phase" | "remaining_ms" | "duration_ms">;

/**
 * Time left on the open question. `remaining_ms` was true when the state arrived at
 * `receivedAt` (performance.now()), so it counts down locally from there.
 */
export function countdown(state: Timing, receivedAt: number | null, now: number): Countdown {
  const ms = remainingMs(state, receivedAt, now) ?? 0;
  const total = state.duration_ms && state.duration_ms > 0 ? state.duration_ms : Math.max(ms, 1);
  return {
    ms,
    seconds: Math.ceil(ms / 1000),
    pct: Math.min(100, (ms / total) * 100),
    warn: ms < WARN_MS,
  };
}

/** performance.now(), refreshed every `intervalMs` while `active`. */
export function useNow(active: boolean, intervalMs = 200): number {
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setNow(performance.now()), intervalMs);
    return () => clearInterval(id);
  }, [active, intervalMs]);
  return now;
}

/** The open question's countdown, re-rendered every 200 ms. */
export function useCountdown(state: Timing, receivedAt: number | null): Countdown {
  const now = useNow(state.phase === "open");
  return countdown(state, receivedAt, now);
}
