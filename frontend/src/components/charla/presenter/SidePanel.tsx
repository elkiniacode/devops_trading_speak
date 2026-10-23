"use client";

import { useState } from "react";

import type { AdminView, Quote } from "@/lib/charla/types";

import styles from "./presenter.module.css";

const ALL = "TODOS";

interface Props {
  view: AdminView;
  busy: boolean;
  exportUrl: string;
  onHideQuote: (quote: Quote) => void;
  onVerification: (on: boolean) => void;
  onReclassify: () => void;
  onResetAll: () => void;
}

/** Right column: open answers by theme, room counts, email stats and admin tools. */
export function SidePanel({ view, busy, exportUrl, onHideQuote, onVerification, onReclassify, onResetAll }: Props) {
  const [theme, setTheme] = useState(ALL);
  const [confirming, setConfirming] = useState(false);
  const [typed, setTyped] = useState("");
  const { counts, email, state } = view;
  const quotes = theme === ALL ? view.quotes : view.quotes.filter((q) => q.theme === theme);
  const chips = [{ name: ALL, count: view.quotes.length }, ...view.themes];

  function closeReset() {
    setConfirming(false);
    setTyped("");
  }

  return (
    <aside className={styles.rightCol} aria-label="Respuestas abiertas y sala">
      <div className={styles.colHead}>
        <span className="c-label">RESPUESTAS ABIERTAS</span>
        <span className={styles.colHeadValue}>{view.quotes.length}</span>
      </div>
      <div className={styles.chips}>
        {chips.map((c) => (
          <button
            key={c.name}
            type="button"
            className={styles.themeChip}
            aria-pressed={theme === c.name}
            onClick={() => setTheme(c.name)}
          >
            {c.name.toUpperCase()} · {c.count}
          </button>
        ))}
      </div>
      <ul className={`${styles.quotes} c-col`} data-testid="pres-quotes">
        {quotes.length === 0 ? <li className={styles.empty}>Aún no hay respuestas abiertas.</li> : null}
        {quotes.map((q) => (
          <li key={q.answer_id} className={styles.quote} data-hidden={q.hidden ? "true" : undefined}>
            <span className={styles.quoteText}>“{q.text}”</span>
            <span className={styles.quoteMeta}>
              <span>{q.username}</span>
              <span className={styles.quoteTheme}>{q.theme ? q.theme.toUpperCase() : "clasificando…"}</span>
            </span>
            <button
              type="button"
              className={styles.miniBtn}
              disabled={busy}
              onClick={() => onHideQuote(q)}
              data-testid={`pres-quote-hide-${q.answer_id}`}
            >
              {q.hidden ? "MOSTRAR" : "OCULTAR"}
            </button>
          </li>
        ))}
      </ul>

      <div className={styles.rightFoot}>
        <div className={styles.countGrid}>
          <div>
            <b>{counts.registered}</b>
            <span>REGISTRADOS</span>
          </div>
          <div>
            <b>{counts.verified}</b>
            <span>VERIFICADOS</span>
          </div>
          <div>
            <b>{counts.with_phone}</b>
            <span>CON CELULAR</span>
          </div>
        </div>
        <div className={styles.footRow} data-testid="pres-email">
          <span>CORREOS</span>
          <b>
            {email.sent} enviados · {email.failed} fallidos{email.queued ? ` · ${email.queued} en cola` : ""}
          </b>
        </div>
        {email.failed > 0 && email.last_error ? <p className={styles.amberNote}>{email.last_error}</p> : null}
        <div className={styles.footRow}>
          <span>Verificación por correo</span>
          <button
            type="button"
            role="switch"
            aria-checked={state.verification_on}
            className={styles.switch}
            disabled={busy}
            onClick={() => onVerification(!state.verification_on)}
            data-testid="pres-verification"
          >
            <span className={styles.switchKnob} />
          </button>
        </div>
        <div className={styles.footBtns}>
          <a className={styles.outlineBtn} href={exportUrl} download data-testid="pres-export">
            EXPORTAR CSV
          </a>
          <button type="button" className={styles.outlineBtn} disabled={busy} onClick={onReclassify}>
            RECLASIFICAR
          </button>
        </div>
        <button
          type="button"
          className={styles.dangerLink}
          onClick={() => setConfirming(true)}
          data-testid="pres-reset-all"
        >
          Reiniciar todo
        </button>
      </div>

      {confirming ? (
        <div
          className={styles.overlay}
          role="dialog"
          aria-modal="true"
          aria-label="Reiniciar todo"
          onKeyDown={(e) => {
            if (e.key === "Escape") closeReset();
          }}
        >
          <form
            className={`${styles.dialog} c-card`}
            onSubmit={(e) => {
              e.preventDefault();
              if (typed !== "RESET") return;
              closeReset();
              onResetAll();
            }}
          >
            <span className={styles.dangerTitle}>REINICIAR TODO</span>
            <p className={styles.why}>
              Borra asistentes, respuestas y sesiones, y vuelve al paso 1. Escribe RESET para confirmar.
            </p>
            <input
              className="c-fld"
              value={typed}
              autoFocus
              onChange={(e) => setTyped(e.target.value)}
              aria-label="Escribe RESET"
              data-testid="pres-reset-input"
            />
            <div className={styles.footBtns}>
              <button type="button" className={styles.outlineBtn} onClick={closeReset}>
                CANCELAR
              </button>
              <button
                type="submit"
                className={styles.dangerBtn}
                disabled={typed !== "RESET"}
                data-testid="pres-reset-confirm"
              >
                BORRAR TODO
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </aside>
  );
}
