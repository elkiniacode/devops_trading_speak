import { fmtPoints } from "@/lib/charla/format";
import type { Me } from "@/lib/charla/types";

import s from "../Sala.module.css";

/** The closing step: final score, final place and a goodbye. */
export function EndView({ me }: { me: Me }) {
  return (
    <div className={`${s.view} ${s.centered} ${s.rise}`}>
      <span className={s.kicker}>GRACIAS POR PARTICIPAR</span>
      <h1 className={`holo ${s.title}`}>Terminaste la charla</h1>
      <div className={s.final}>
        <div>
          <div className={s.finalLabel}>PUNTAJE FINAL</div>
          <div className={`${s.finalValue} ${s.finalScore}`} data-testid="sala-final-score">
            {fmtPoints(me.score)}
          </div>
        </div>
        <div className={s.right}>
          <div className={s.finalLabel}>PUESTO</div>
          <div className={s.finalValue}>{me.rank ? `#${me.rank}` : "—"}</div>
        </div>
      </div>
      <p className={s.lead}>
        {me.phone_status === "given"
          ? "Te escribiremos por WhatsApp con tu puesto final y las diapositivas."
          : "Los resultados finales se muestran en la pantalla principal."}
      </p>
    </div>
  );
}
