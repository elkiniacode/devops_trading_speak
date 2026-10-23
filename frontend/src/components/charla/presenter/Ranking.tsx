"use client";

import { fmtPoints } from "@/lib/charla/format";
import type { RankingRow } from "@/lib/charla/types";

import { adminTop, projectedTop } from "./logic";
import styles from "./presenter.module.css";

interface Props {
  ranking: RankingRow[];
  projection: boolean;
  busy: boolean;
  onToggleHide: (row: RankingRow) => void;
}

const PODIUM_ORDER = [1, 0, 2]; // 2nd, 1st, 3rd

/** Top 10 with a podium for the top 3. Big type: this goes on the projector. */
export function Ranking({ ranking, projection, busy, onToggleHide }: Props) {
  const visible = projectedTop(ranking, 10);
  const podium = PODIUM_ORDER.map((i) => visible[i]).filter((r): r is RankingRow => Boolean(r));
  // The presenter also sees hidden attendees inline, so they can be shown again.
  const rows = projection ? visible.slice(3) : adminTop(ranking, 10);

  return (
    <section className={styles.ranking} data-projection={projection ? "true" : undefined}>
      <div className={styles.rankHead}>
        <span className="c-kicker">RANKING · TOP 10</span>
        <h2 className={`holo ${styles.rankTitle}`}>Los más rápidos y certeros</h2>
      </div>
      {visible.length === 0 ? (
        <p className={styles.empty}>Todavía no hay puntajes. Aparecen cuando se revela cada respuesta.</p>
      ) : (
        <div className={styles.podium}>
          {podium.map((r) => (
            <div key={r.attendee_id} className={styles.podiumCard} data-place={r.rank}>
              <span className={styles.podiumPlace}>#{r.rank}</span>
              <span className={styles.podiumName}>{r.username}</span>
              <span className={styles.podiumScore}>{fmtPoints(r.score)} PTS</span>
              <span className={styles.podiumCorrect}>{r.correct} correctas</span>
            </div>
          ))}
        </div>
      )}
      <ol className={`${styles.rankList} c-col`} data-testid="pres-ranking">
        {rows.map((r) => {
          const place = projection ? r.rank : (visible.find((v) => v.attendee_id === r.attendee_id)?.rank ?? null);
          return (
            <li
              key={r.attendee_id}
              className={styles.rankRow}
              data-hidden={r.hidden ? "true" : undefined}
              data-username={r.username}
            >
              <span className={styles.rankPlace}>{place ? `#${place}` : "—"}</span>
              <span className={styles.rankName}>{r.username}</span>
              <span className={styles.rankCorrect}>{r.correct} ✓</span>
              <span className={styles.rankScore}>{fmtPoints(r.score)}</span>
              {projection ? null : (
                <button
                  type="button"
                  className={styles.miniBtn}
                  disabled={busy}
                  onClick={() => onToggleHide(r)}
                  data-testid={`pres-rank-hide-${r.attendee_id}`}
                >
                  {r.hidden ? "MOSTRAR" : "OCULTAR"}
                </button>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
