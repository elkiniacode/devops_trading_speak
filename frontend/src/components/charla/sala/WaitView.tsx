import type { RoomState } from "@/lib/charla/types";

import s from "../Sala.module.css";
import { MAX_POINTS, Stat } from "./parts";

/** Between questions: a pulsing beacon and the room's numbers. */
export function WaitView({ state }: { state: RoomState }) {
  const first = state.step === 0;
  return (
    <div className={`${s.view} ${s.centered} ${s.rise}`}>
      <div className={s.beacon} aria-hidden="true">
        <span className={s.ring} />
        <span className={s.dot} />
      </div>
      <div className={s.stack}>
        <span className={s.kicker}>ESTÁS DENTRO</span>
        <h1 className={`holo ${s.title}`}>
          {first ? "Esperando la primera pregunta" : "Esperando la siguiente pregunta"}
        </h1>
        <p className={s.lead}>
          Mantén esta pantalla abierta. Cuando el presentador lance una pregunta, aparece aquí. Gana más puntos entre
          más rápido respondas.
        </p>
      </div>
      <div className={s.stats}>
        <Stat value={state.total_quiz} label="PREGUNTAS" />
        <Stat value={state.room_count} label="EN LA SALA" />
        <Stat value={MAX_POINTS} label="MÁX. POR PREG." />
      </div>
    </div>
  );
}
