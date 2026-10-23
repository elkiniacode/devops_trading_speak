import type { ReactNode } from "react";

import s from "../Sala.module.css";
import type { Countdown } from "./countdown";

export const LETTERS = ["A", "B", "C", "D"] as const;

/** Most points one quiz question can give (500 base + 500 for speed). */
export const MAX_POINTS = 1000;

/** "José Pérez" -> "JP", "ana_m" -> "AM", "Lu" -> "LU". */
export function initials(username: string): string {
  const words = username.trim().split(/[\s._-]+/).filter(Boolean);
  if (words.length === 0) return "?";
  const chars =
    words.length > 1 ? [Array.from(words[0])[0], Array.from(words[1])[0]] : Array.from(words[0]).slice(0, 2);
  return chars.join("").toLocaleUpperCase("es-CO");
}

export function Stat({ value, label, accent = false }: { value: ReactNode; label: string; accent?: boolean }) {
  return (
    <div className={accent ? `${s.stat} ${s.statAccent}` : s.stat}>
      <div className={s.statValue}>{value}</div>
      <div className={s.statLabel}>{label}</div>
    </div>
  );
}

/** Label, seconds left and a draining bar; red under 5 s. */
export function Timer({ t, label, labelClass = s.kicker }: { t: Countdown; label: string; labelClass?: string }) {
  return (
    <div className={t.warn ? `${s.stack} ${s.warn}` : s.stack} data-testid="sala-timer" data-warn={t.warn}>
      <div className={s.qHead}>
        <span className={labelClass}>{label}</span>
        <span className={s.time} data-testid="sala-seconds">
          {t.seconds}s
        </span>
      </div>
      <div className={s.bar}>
        <div className={s.barFill} style={{ width: `${t.pct}%` }} />
      </div>
    </div>
  );
}

export function CheckIcon({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <path d="M6 17 L13 24 L26 8" fill="none" stroke="currentColor" strokeWidth="3" />
    </svg>
  );
}

export function CrossIcon({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 30 30" aria-hidden="true">
      <path d="M6 6 L24 24 M24 6 L6 24" fill="none" stroke="currentColor" strokeWidth="3" />
    </svg>
  );
}

export function ClockIcon({ size = 30 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" aria-hidden="true">
      <circle cx="7" cy="7" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.2" />
      <path d="M7 3.5 V7 L9.5 8.5" fill="none" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}
