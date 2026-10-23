import { useId } from "react";

import type { RoomState } from "@/lib/charla/types";
import { OPEN_MAX_CHARS, openTextError } from "@/lib/charla/validate";

import s from "../Sala.module.css";
import { useCountdown } from "./countdown";
import { Timer } from "./parts";

/** The open question: free text, shown on the big screen with the attendee's username. */
export function OpenView({
  state,
  receivedAt,
  draft,
  onDraft,
  onSend,
}: {
  state: RoomState;
  receivedAt: number | null;
  draft: string;
  onDraft: (text: string) => void;
  onSend: (text: string) => void;
}) {
  const id = useId();
  const t = useCountdown(state, receivedAt);
  const ready = openTextError(draft) === null;
  return (
    <form
      className={`${s.view} ${s.rise}`}
      onSubmit={(e) => {
        e.preventDefault();
        if (ready) onSend(draft.trim());
      }}
    >
      <Timer t={t} label="PREGUNTA ABIERTA · +100 PTS" labelClass={`${s.kicker} ${s.kickerOpen}`} />
      <label htmlFor={id} className={s.question}>
        {state.question?.text}
      </label>
      <textarea
        id={id}
        className={s.ta}
        placeholder={state.question?.placeholder ?? ""}
        value={draft}
        maxLength={OPEN_MAX_CHARS}
        onChange={(e) => onDraft(e.target.value)}
        data-testid="sala-open-text"
      />
      <div className={s.counter}>
        <span>Se mostrará en pantalla con tu nombre de usuario.</span>
        <span>
          {draft.length}/{OPEN_MAX_CHARS}
        </span>
      </div>
      <div className={s.actions}>
        <button type="submit" className={s.btn} disabled={!ready} data-testid="sala-open-send">
          ENVIAR RESPUESTA
        </button>
      </div>
    </form>
  );
}
