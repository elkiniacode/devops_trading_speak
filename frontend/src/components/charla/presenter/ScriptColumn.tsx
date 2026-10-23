"use client";

import type { AdminState, ScriptStep } from "@/lib/charla/types";

import { STEP_TAG, phoneTimeLabel } from "./logic";
import styles from "./presenter.module.css";

interface Props {
  script: ScriptStep[];
  state: AdminState;
  busy: boolean;
  onGoto: (step: number) => void;
}

/** Left column: the 9-step talk script; click a step to jump to it. */
export function ScriptColumn({ script, state, busy, onGoto }: Props) {
  const phoneAt = phoneTimeLabel(state.phone_prompt_at);
  return (
    <aside className={styles.leftCol} aria-label="Guion de la charla">
      <div className={styles.colHead}>
        <span className="c-label">GUION DE LA CHARLA</span>
        <span className={styles.colHeadValue}>
          {state.step + 1}/{script.length || 9}
        </span>
      </div>
      <ol className={`${styles.steps} c-col`}>
        {script.map((s) => {
          const mark = s.step < state.step ? "done" : s.step === state.step ? "active" : "pending";
          return (
            <li key={s.step}>
              <button
                type="button"
                className={styles.step}
                data-state={mark}
                data-kind={s.kind}
                aria-current={mark === "active" ? "step" : undefined}
                disabled={busy}
                onClick={() => onGoto(s.step)}
                data-testid={`pres-step-${s.step}`}
              >
                <span className={styles.stepNum}>{mark === "done" ? "✓" : s.step + 1}</span>
                <span className={styles.stepText}>
                  <span className={styles.stepTitle}>{s.title}</span>
                  <span className={styles.stepTag}>{STEP_TAG[s.kind]}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      <div className={styles.colFoot}>
        <svg width="14" height="14" className={styles.clockIcon} aria-hidden="true">
          <circle cx="7" cy="7" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
          <path d="M7 3.5 V7 L9.5 8.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
        </svg>
        <span data-testid="pres-phone-at">
          {state.phone_prompt ? (
            <>
              Solicitud de celular <b>activa</b>
            </>
          ) : phoneAt ? (
            <>
              Solicitud de celular automática a las <b>{phoneAt}</b>
            </>
          ) : (
            <>
              Solicitud de celular automática <b>desactivada</b>
            </>
          )}
        </span>
      </div>
    </aside>
  );
}
