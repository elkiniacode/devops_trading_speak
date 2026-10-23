/** Pure helpers for the presenter panel: labels, button gating, ranking cuts and timers. */
import type { AdminState, Phase, RankingRow, StepKind } from "@/lib/charla/types";

export const LETTERS = ["A", "B", "C", "D"] as const;

/** The closing step; SIGUIENTE stops here. */
export const LAST_STEP = 8;

export const PHASE_LABEL: Record<Phase, string> = {
  idle: "EN ESPERA",
  open: "RECIBIENDO RESPUESTAS",
  closed: "CERRADA",
  revealed: "RESPUESTA REVELADA",
};

/** Small caps tag under each script step. */
export const STEP_TAG: Record<StepKind, string> = {
  quiz: "QUIZ · 1000 PTS",
  open: "PREGUNTA ABIERTA",
  closing: "CIERRE",
};

/** Kicker above the centre title, e.g. "QUIZ · PREGUNTA 3 DE 7". */
export function kindLabel(state: Pick<AdminState, "kind" | "number" | "total_quiz">): string {
  if (state.kind === "quiz") return `QUIZ · PREGUNTA ${state.number ?? "?"} DE ${state.total_quiz}`;
  return STEP_TAG[state.kind];
}

export type Action = "launch" | "phoneNow" | "close" | "reveal" | "next" | "resetStep";

export interface ButtonState {
  label: string;
  enabled: boolean;
}

export interface Controls {
  /** LANZAR PREGUNTA, or the phone request at the closing step. */
  launch: ButtonState & { action: "launch" | "phoneNow" };
  close: ButtonState;
  reveal: ButtonState;
  next: ButtonState;
  resetStep: ButtonState;
}

/** Which presenter buttons make sense right now (the backend still has the last word: 409). */
export function controlsFor(
  state: Pick<AdminState, "kind" | "phase" | "step" | "phone_prompt">,
  answered: number,
): Controls {
  const { kind, phase } = state;
  const closing = kind === "closing";
  let launch: Controls["launch"];
  if (closing) {
    launch = state.phone_prompt
      ? { label: "SOLICITUD ENVIADA", enabled: false, action: "phoneNow" }
      : { label: "LANZAR SOLICITUD AHORA", enabled: true, action: "phoneNow" };
  } else {
    launch =
      phase === "idle"
        ? { label: "LANZAR PREGUNTA", enabled: true, action: "launch" }
        : { label: "LANZADA", enabled: false, action: "launch" };
  }
  return {
    launch,
    close: { label: "CERRAR RESPUESTAS", enabled: !closing && phase === "open" },
    reveal: {
      label: kind === "open" ? "MOSTRAR EN PANTALLA" : "REVELAR RESPUESTA",
      enabled: !closing && phase === "closed",
    },
    next: { label: "SIGUIENTE →", enabled: state.step < LAST_STEP },
    resetStep: { label: "Reiniciar pregunta", enabled: !closing && (phase !== "idle" || answered > 0) },
  };
}

/** Whole-number percentage, 0 when there is nothing to divide by. */
export function pct(part: number, whole: number): number {
  if (!whole || whole <= 0) return 0;
  return Math.round((part / whole) * 100);
}

/** Bar widths relative to the largest value, so the leader always fills the track. */
export function barWidths(values: number[]): number[] {
  const max = Math.max(1, ...values);
  return values.map((v) => Math.round((v / max) * 100));
}

/** "15:50" -> "3:50 p. m." (es-CO style); null stays null. */
export function phoneTimeLabel(hhmm: string | null): string | null {
  if (!hhmm) return null;
  const match = /^(\d{1,2}):(\d{2})$/.exec(hhmm.trim());
  if (!match) return hhmm;
  const h = Number(match[1]);
  const suffix = h < 12 ? "a. m." : "p. m.";
  const h12 = h % 12 === 0 ? 12 : h % 12;
  return `${h12}:${match[2]} ${suffix}`;
}

/** Text for the TIEMPO RESTANTE counter. `seconds` is the live countdown while open. */
export function timeText(
  state: Pick<AdminState, "kind" | "phase" | "duration_ms">,
  seconds: number | null,
): string {
  if (state.kind === "closing") return "—";
  if (state.phase === "open") return `${seconds ?? 0} s`;
  if (state.phase === "idle" && state.duration_ms) return `${Math.round(state.duration_ms / 1000)} s`;
  return "0 s";
}

/**
 * Rows for the presenter's ranking: walk the list until `n` visible attendees are in,
 * keeping hidden ones inline so they can be shown again.
 */
export function adminTop(ranking: RankingRow[], n: number): RankingRow[] {
  const rows: RankingRow[] = [];
  let visible = 0;
  for (const row of ranking) {
    if (visible >= n) break;
    rows.push(row);
    if (!row.hidden) visible += 1;
  }
  return rows;
}

/** The projected ranking: hidden attendees left out and places renumbered without gaps. */
export function projectedTop(ranking: RankingRow[], n: number): RankingRow[] {
  return ranking
    .filter((row) => !row.hidden)
    .slice(0, n)
    .map((row, i) => ({ ...row, rank: i + 1 }));
}

/** True when a keyboard shortcut should be ignored because the user is typing. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!target || !(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

/** Shortcut key -> what it does. Arrow keys come through as "ArrowRight". */
export type Shortcut = "launch" | "close" | "reveal" | "next" | "projection" | "qr" | "escape";

export function shortcutFor(key: string): Shortcut | null {
  switch (key) {
    case "l":
    case "L":
      return "launch";
    case "c":
    case "C":
      return "close";
    case "r":
    case "R":
      return "reveal";
    case "ArrowRight":
      return "next";
    case "p":
    case "P":
      return "projection";
    case "q":
    case "Q":
      return "qr";
    case "Escape":
      return "escape";
    default:
      return null;
  }
}
