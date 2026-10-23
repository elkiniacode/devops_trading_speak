"use client";

import type { ThemeCount } from "@/lib/charla/types";

import { LETTERS, barWidths } from "./logic";
import styles from "./presenter.module.css";

interface DistributionProps {
  options: string[];
  counts: number[];
  /** Index of the correct option, highlighted only when `revealed`; null for a poll. */
  answer: number | null;
  revealed: boolean;
  big?: boolean;
}

/** A–D answer bars. After the reveal the correct one glows and the rest dim. */
export function DistributionBars({ options, counts, answer, revealed, big = false }: DistributionProps) {
  const values = options.map((_, i) => counts[i] ?? 0);
  const widths = barWidths(values);
  return (
    <ul className={styles.bars} data-size={big ? "big" : "normal"} data-testid="pres-distribution">
      {options.map((text, i) => {
        const mark = !revealed || answer === null ? "live" : i === answer ? "correct" : "dim";
        return (
          <li key={i} className={styles.barRow} data-mark={mark} data-testid={`pres-option-${i}`}>
            <span className={styles.barKey}>{LETTERS[i] ?? i + 1}</span>
            <span className={styles.barBody}>
              <span className={styles.barText}>{text}</span>
              <span className={styles.barTrack}>
                <span className={`${styles.barFill} anim`} style={{ width: `${widths[i]}%` }} />
              </span>
            </span>
            <span className={styles.barCount}>{values[i]}</span>
          </li>
        );
      })}
    </ul>
  );
}

/** Fuchsia bars for the themes the AI found in the open answers. */
export function ThemeBars({ themes, big = false }: { themes: ThemeCount[]; big?: boolean }) {
  const widths = barWidths(themes.map((t) => t.count));
  return (
    <ul className={styles.themeBars} data-size={big ? "big" : "normal"} data-testid="pres-themes">
      {themes.map((t, i) => (
        <li key={t.name} className={styles.themeRow}>
          <span className={styles.themeName}>{t.name}</span>
          <span className={styles.barTrack}>
            <span className={`${styles.themeFill} anim`} style={{ width: `${widths[i]}%` }} />
          </span>
          <span className={styles.themeCount}>{t.count}</span>
        </li>
      ))}
    </ul>
  );
}
