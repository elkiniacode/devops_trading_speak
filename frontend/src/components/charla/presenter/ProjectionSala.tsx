"use client";

import { useEffect, useState } from "react";

import { remainingSeconds } from "@/lib/charla/format";
import type { AdminView } from "@/lib/charla/types";

import { DistributionBars, ThemeBars } from "./Bars";
import { useTicker } from "./hooks";
import { kindLabel, pct } from "./logic";
import styles from "./presenter.module.css";

/**
 * What the room sees on the projector: a big title and, depending on the phase, the answer
 * count (while a question is open, so nobody copies the crowd), the distribution or the themes.
 */
export function ProjectionSala({ view, receivedAt }: { view: AdminView; receivedAt: number | null }) {
  const { state, counts } = view;
  const open = state.phase === "open";
  const now = useTicker(250, open);
  const seconds = remainingSeconds(state, receivedAt, now);
  const [joinUrl, setJoinUrl] = useState("/charla/");
  useEffect(() => setJoinUrl(`${window.location.host}/charla/`), []);
  const step = view.script[state.step];
  const title = state.question?.text ?? step?.title ?? "";

  let body = null;
  if (state.kind === "closing") {
    body = (
      <div className={styles.projCount}>
        <span className={styles.projBig}>{counts.with_phone}</span>
        <span className={styles.projSub}>de {counts.active} asistentes dejaron su celular</span>
      </div>
    );
  } else if (state.phase === "idle") {
    body = <p className={styles.projSub}>Prepárate: la pregunta aparece en tu celular.</p>;
  } else if (open) {
    body = (
      <div className={styles.projCount} data-testid="pres-proj-count">
        <span className={styles.projBig}>{counts.answered}</span>
        <span className={styles.projSub}>
          de {counts.active} ya respondieron · {seconds ?? 0} s
        </span>
      </div>
    );
  } else if (state.kind === "quiz") {
    const revealed = state.phase === "revealed";
    const why = revealed ? (state.reveal?.why ?? step?.why ?? null) : null;
    body = (
      <>
        <DistributionBars
          big
          options={step?.options.length ? step.options : (state.question?.options ?? [])}
          counts={view.distribution ?? state.reveal?.distribution ?? []}
          answer={state.reveal?.answer ?? step?.answer ?? null}
          revealed={revealed}
        />
        {why ? <p className={styles.projWhy}>{why}</p> : null}
        <span className={styles.projSub}>
          {counts.answered} respuestas · {pct(counts.answered, counts.active)}% de la sala
        </span>
      </>
    );
  } else {
    const quotes = state.phase === "revealed" ? view.quotes.filter((q) => !q.hidden).slice(0, 6) : [];
    body = (
      <div className={styles.projOpen}>
        <ThemeBars big themes={view.themes} />
        {quotes.length ? (
          <ul className={styles.projQuotes}>
            {quotes.map((q) => (
              <li key={q.answer_id} className={styles.quote}>
                <span className={styles.quoteText}>“{q.text}”</span>
                <span className={styles.quoteMeta}>
                  <span>{q.username}</span>
                  <span className={styles.quoteTheme}>{q.theme?.toUpperCase() ?? ""}</span>
                </span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    );
  }

  return (
    <section className={styles.projection} data-testid="pres-projection">
      <span className={styles.kind} data-kind={state.kind}>
        {kindLabel(state)}
      </span>
      <h2 className={`holo ${styles.projTitle}`}>{state.kind === "closing" ? step?.title || title : title}</h2>
      <div className={styles.projBody}>{body}</div>
      <span className={styles.projJoin}>Entra en {joinUrl}</span>
    </section>
  );
}
