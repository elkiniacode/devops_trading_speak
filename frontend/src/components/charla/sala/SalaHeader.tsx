import { fmtPoints } from "@/lib/charla/format";
import type { Me } from "@/lib/charla/types";

import s from "../Sala.module.css";
import { initials } from "./parts";

/** Logo on the left; username, score and the chamfered initials badge on the right. */
export function SalaHeader({ me }: { me: Me | null }) {
  return (
    <header className={s.header}>
      <img src="/charla/logo.png" alt="IA Revolutions" className={s.logo} />
      {me && (
        <div className={s.who}>
          <div className={s.whoText}>
            <span className={s.username} data-testid="sala-username">
              {me.username}
            </span>
            <span className={s.score} data-testid="sala-score">
              {fmtPoints(me.score)} PTS
            </span>
          </div>
          <span className={s.badge} aria-hidden="true">
            {initials(me.username)}
          </span>
        </div>
      )}
    </header>
  );
}
