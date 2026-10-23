"use client";

import type { ReactNode } from "react";

import { remainingSeconds } from "@/lib/charla/format";
import type { AdminView } from "@/lib/charla/types";

import { DistributionBars, ThemeBars } from "./Bars";
import { useTicker } from "./hooks";
import { type Action, PHASE_LABEL, controlsFor, kindLabel, pct, phoneTimeLabel, timeText } from "./logic";
import styles from "./presenter.module.css";

function Stat({ label, value, accent = false }: { label: string; value: ReactNode; accent?: boolean }) {
  return (
    <div className={styles.stat}>
      <div className={styles.statValue} data-accent={accent ? "true" : undefined}>
        {value}
      </div>
      <div className={styles.statLabel}>{label}</div>
    </div>
  );
}

/** Title, ESTADO badge, live counters (with a local countdown) and the stage-specific body. */
export function QuestionHead({ view, receivedAt }: { view: AdminView; receivedAt: number | null }) {
  const { state, counts } = view;
  const now = useTicker(250, state.phase === "open");
  const seconds = remainingSeconds(state, receivedAt, now);
  const title = state.question?.text ?? view.script[state.step]?.title ?? "";
  return (
    <>
      <div className={styles.titleRow}>
        <div className={styles.titleBlock}>
          <span className={styles.kind} data-kind={state.kind}>
            {kindLabel(state)}
          </span>
          <h2 className={`holo ${styles.title}`} data-testid="pres-title">
            {title}
          </h2>
        </div>
        <div className={styles.phaseBlock}>
          <span className="c-label">ESTADO</span>
          <span className={styles.phase} data-phase={state.phase} data-testid="pres-phase">
            {PHASE_LABEL[state.phase]}
          </span>
        </div>
      </div>
      <div className={styles.stats}>
        <Stat
          label="RESPUESTAS"
          value={
            <>
              <span data-testid="pres-answered">{counts.answered}</span>
              <small> / {counts.active}</small>
            </>
          }
        />
        <Stat label="PARTICIPACIÓN" value={`${pct(counts.answered, counts.active)}%`} />
        <Stat label="ACIERTO" accent value={state.kind === "quiz" ? `${pct(counts.correct, counts.answered)}%` : "—"} />
        <Stat label="TIEMPO RESTANTE" value={<span data-testid="pres-time">{timeText(state, seconds)}</span>} />
      </div>
    </>
  );
}

/** Body of the centre column for the current step's kind. */
export function QuestionBody({ view }: { view: AdminView }) {
  const { state, counts } = view;
  if (state.kind === "quiz" || state.kind === "poll") {
    const step = view.script[state.step];
    const options = step?.options.length ? step.options : (state.question?.options ?? []);
    const revealed = state.phase === "revealed";
    const why = revealed ? (state.reveal?.why ?? step?.why ?? null) : null;
    return (
      <div className={styles.panelBox}>
        <span className="c-label">DISTRIBUCIÓN DE RESPUESTAS</span>
        <DistributionBars
          options={options}
          counts={view.distribution ?? state.reveal?.distribution ?? []}
          answer={state.reveal?.answer ?? step?.answer ?? null}
          revealed={revealed}
        />
        {why ? <p className={styles.why}>{why}</p> : null}
      </div>
    );
  }
  if (state.kind === "open") {
    return (
      <div className={styles.panelBox}>
        <span className="c-label">
          {view.themes.length ? "TEMAS DETECTADOS POR IA · " : "RESPUESTAS ABIERTAS · "}
          {counts.answered} RESPUESTAS
        </span>
        <ThemeBars themes={view.themes} />
      </div>
    );
  }
  const at = phoneTimeLabel(state.phone_prompt_at);
  return (
    <div className={styles.panelBox}>
      <span className="c-label">CAPTURA DE CELULARES</span>
      <div className={styles.phoneBig}>
        <span className={styles.phoneCount} data-testid="pres-with-phone">
          {counts.with_phone}
        </span>
        <span className={styles.phoneText}>de {counts.active} asistentes dejaron su celular con autorización</span>
      </div>
      <span className={styles.barTrack}>
        <span className={styles.phoneFill} style={{ width: `${pct(counts.with_phone, counts.active)}%` }} />
      </span>
      <p className={styles.why}>
        {state.phone_prompt
          ? "La solicitud ya está en el celular de cada asistente."
          : at
            ? `La solicitud se muestra sola en el celular de cada asistente a las ${at} También puedes lanzarla ahora.`
            : "La solicitud automática está desactivada. Lánzala cuando quieras."}
      </p>
    </div>
  );
}

interface ControlsProps {
  view: AdminView;
  busy: boolean;
  onAction: (action: Action) => void;
}

/** LANZAR / CERRAR / REVELAR / SIGUIENTE, each enabled only in its phase. */
export function ControlBar({ view, busy, onAction }: ControlsProps) {
  const c = controlsFor(view.state, view.counts.answered);
  return (
    <>
      <div className={styles.controls}>
        <button
          type="button"
          className={styles.ctl}
          data-variant="launch"
          disabled={busy || !c.launch.enabled}
          onClick={() => onAction(c.launch.action)}
          data-testid="pres-launch"
          title="L"
        >
          {c.launch.label}
        </button>
        <button
          type="button"
          className={styles.ctl}
          data-variant="close"
          disabled={busy || !c.close.enabled}
          onClick={() => onAction("close")}
          data-testid="pres-close"
          title="C"
        >
          {c.close.label}
        </button>
        <button
          type="button"
          className={styles.ctl}
          data-variant="reveal"
          disabled={busy || !c.reveal.enabled}
          onClick={() => onAction("reveal")}
          data-testid="pres-reveal"
          title="R"
        >
          {c.reveal.label}
        </button>
        <button
          type="button"
          className={styles.ctl}
          data-variant="next"
          disabled={busy || !c.next.enabled}
          onClick={() => onAction("next")}
          data-testid="pres-next"
          title="→"
        >
          {c.next.label}
        </button>
      </div>
      <div className={styles.controlsFoot}>
        <button
          type="button"
          className={styles.linkBtn}
          disabled={busy || !c.resetStep.enabled}
          onClick={() => onAction("resetStep")}
          data-testid="pres-reset-step"
        >
          {c.resetStep.label}
        </button>
        <span className={styles.hint}>L lanzar · C cerrar · R revelar · → siguiente · P proyectar · Q QR</span>
      </div>
    </>
  );
}
