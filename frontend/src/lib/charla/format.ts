import type { RoomState } from "./types";

/** 1820 -> "1.820" (Colombian grouping). */
export function fmtPoints(n: number): string {
  return Math.round(n).toLocaleString("es-CO");
}

type Countdown = Pick<RoomState, "phase" | "remaining_ms">;

/**
 * Milliseconds left on the open question, counted down locally from the moment the state
 * arrived (`receivedAt`, a performance.now() value). Null when no question is open.
 */
export function remainingMs(state: Countdown, receivedAt: number | null, now: number = performance.now()): number | null {
  if (state.phase !== "open" || state.remaining_ms === null) return null;
  const elapsed = receivedAt === null ? 0 : Math.max(0, now - receivedAt);
  return Math.max(0, state.remaining_ms - elapsed);
}

/** Whole seconds left, rounded up so "1" shows until the very end. Null when not open. */
export function remainingSeconds(state: Countdown, receivedAt: number | null, now: number = performance.now()): number | null {
  const ms = remainingMs(state, receivedAt, now);
  return ms === null ? null : Math.ceil(ms / 1000);
}
