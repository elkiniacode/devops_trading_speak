import type { ReactNode } from "react";

import { fmtPoints } from "@/lib/charla/format";
import type { Me, RoomState } from "@/lib/charla/types";

import s from "../Sala.module.css";
import { CheckIcon, ClockIcon, CrossIcon, LETTERS, Stat } from "./parts";

const BASE_POINTS = 500;

/** After the reveal: right or wrong, points won, the correct answer and my standing. */
export function ResultView({ state, me }: { state: RoomState; me: Me }) {
  const points = me.result?.points ?? 0;
  const isOpen = state.kind === "open";

  let tone: string;
  let icon: ReactNode;
  let title: string;
  let note: string;
  if (isOpen) {
    const shared = points > 0;
    tone = shared ? s.ok : s.late;
    icon = shared ? <CheckIcon /> : <ClockIcon />;
    title = shared ? "PREGUNTA ABIERTA" : "SIN RESPUESTA";
    note = shared ? "¡Gracias por compartir!" : "Esta vez no enviaste respuesta.";
  } else if (!me.answer || me.answer.choice === null) {
    // me.result is always present after a reveal; no answer means time ran out.
    tone = s.late;
    icon = <ClockIcon />;
    title = "SE ACABÓ EL TIEMPO";
    note = "Sin puntos esta vez";
  } else if (me.result?.correct) {
    tone = s.ok;
    icon = <CheckIcon />;
    title = "CORRECTO";
    note = `${BASE_POINTS} base + ${Math.max(0, points - BASE_POINTS)} por velocidad`;
  } else {
    tone = s.bad;
    icon = <CrossIcon />;
    title = "NO ERA ESA";
    note = "Sin puntos esta vez";
  }

  const correct = state.reveal?.answer ?? null;
  const options = state.question?.options ?? [];
  const quizCorrect = isOpen ? undefined : me.result?.correct === true;

  return (
    <div className={`${s.view} ${s.rise}`}>
      <div className={`${s.resultHead} ${tone}`} data-testid="sala-result" data-correct={quizCorrect}>
        <span className={`${s.icon} ${s.pop}`}>{icon}</span>
        <span className={s.resultTitle}>{title}</span>
        <span className={s.gain}>+{fmtPoints(points)}</span>
        <span className={s.gainNote}>{note}</span>
      </div>

      {!isOpen && correct !== null && (
        <div className={s.card}>
          <span className={s.cardLabel}>RESPUESTA CORRECTA</span>
          <span className={s.cardStrong}>
            {LETTERS[correct]}. {options[correct]}
          </span>
          {state.reveal?.why && <span className={s.cardBody}>{state.reveal.why}</span>}
        </div>
      )}

      <div className={s.stats}>
        <Stat accent value={fmtPoints(me.score)} label="TUS PUNTOS" />
        <Stat value={me.rank ? `#${me.rank}` : "—"} label={`PUESTO DE ${state.room_count}`} />
      </div>

      <p className={s.note}>La siguiente pregunta aparece aquí sola.</p>
    </div>
  );
}
