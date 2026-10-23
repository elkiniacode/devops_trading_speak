import type { MyAnswer, RoomState } from "@/lib/charla/types";

import s from "../Sala.module.css";
import { CheckIcon, ClockIcon, LETTERS } from "./parts";

/** After answering (or when time ran out): wait for the presenter's reveal. */
export function AnsweredView({ state, answer }: { state: RoomState; answer: MyAnswer | null }) {
  const isOpen = state.kind === "open";
  const label = `${isOpen ? "PREGUNTA ABIERTA" : "PREGUNTA"} ${state.number ?? ""} / ${state.total_quiz}`;

  if (!answer) {
    return (
      <div className={`${s.view} ${s.centered} ${s.rise}`}>
        <span className={`${s.icon} ${s.iconSm} ${s.late} ${s.pop}`}>
          <ClockIcon size={26} />
        </span>
        <div className={s.stack}>
          <span className={s.kicker}>{label}</span>
          <h1 className={`holo ${s.title}`}>Se acabó el tiempo</h1>
          <p className={s.lead}>
            Esta vez no alcanzaste a responder. Espera a que el presentador revele la respuesta.
          </p>
        </div>
      </div>
    );
  }

  const choice = answer.choice;
  return (
    <div className={`${s.view} ${s.centered} ${s.rise}`}>
      <span className={`${s.icon} ${s.iconSm} ${s.ok} ${s.pop}`}>
        <CheckIcon size={24} />
      </span>
      <div className={s.stack}>
        <span className={isOpen ? `${s.kicker} ${s.kickerOpen}` : s.kicker}>{label}</span>
        <h1 className={`holo ${s.title}`}>Respuesta registrada</h1>
      </div>
      {isOpen ? (
        <div className={`${s.card} ${s.chosenOpen}`}>
          <span className={s.cardLabel}>TU RESPUESTA</span>
          <span className={s.cardBody}>{answer.text}</span>
        </div>
      ) : (
        choice !== null && (
          <div className={`${s.option} ${s.chosen}`} data-testid="sala-chosen">
            <span className={s.optionKey}>{LETTERS[choice]}</span>
            <span className={s.optionText}>{state.question?.options[choice]}</span>
          </div>
        )
      )}
      <p className={s.lead}>
        {isOpen
          ? "Gracias. Tu respuesta puede aparecer en la pantalla principal."
          : "Espera a que el presentador revele la respuesta."}
      </p>
    </div>
  );
}
