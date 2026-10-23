import type { RoomState } from "@/lib/charla/types";

import s from "../Sala.module.css";
import { useCountdown } from "./countdown";
import { LETTERS, Timer } from "./parts";

/** A live quiz question: countdown, the text and four big A–D buttons. */
export function QuestionView({
  state,
  receivedAt,
  onPick,
}: {
  state: RoomState;
  receivedAt: number | null;
  onPick: (choice: number) => void;
}) {
  const t = useCountdown(state, receivedAt);
  // remaining_ms is 0 in the server's grace window: options stay tappable until it closes.
  const timeUp = t.ms <= 0;
  const options = state.question?.options ?? [];
  return (
    <div className={`${s.view} ${s.rise}`}>
      <Timer t={t} label={`PREGUNTA ${state.number ?? ""} / ${state.total_quiz}`} />
      <h2 className={s.question}>{state.question?.text}</h2>
      <div className={s.options}>
        {options.map((text, i) => (
          <button
            key={i}
            type="button"
            className={s.option}
            onClick={() => onPick(i)}
            data-testid={`sala-option-${i}`}
          >
            <span className={s.optionKey}>{LETTERS[i]}</span>
            <span className={s.optionText}>{text}</span>
          </button>
        ))}
      </div>
      <p className={s.note}>
        {timeUp ? "¡Responde ya! Se está cerrando." : "Respuesta correcta = 500 pts + hasta 500 por velocidad"}
      </p>
    </div>
  );
}
