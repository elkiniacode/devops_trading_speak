"use client";

import { type FormEvent, useState } from "react";

import { getMonitorBase, setMonitorBase } from "@/lib/charla/session";
import type { CharlaStreamStatus } from "@/lib/charla/stream";
import type { AdminCounts } from "@/lib/charla/types";

import { useClock } from "./hooks";
import styles from "./presenter.module.css";

export type Tab = "sala" | "ranking";

const STATUS_LABEL: Record<CharlaStreamStatus, string> = {
  live: "EN VIVO",
  connecting: "CONECTANDO",
  reconnecting: "RECONECTANDO",
  offline: "SIN CONEXIÓN",
};

/** Agent-monitor pages, opened in a new tab (not part of this app). */
const MONITOR_PAGES = [
  { label: "AGENTES", page: "Agentes.dc.html" },
  { label: "HISTORIAL", page: "Historial.dc.html" },
  { label: "HILOS", page: "Hilos.dc.html" },
] as const;

interface Props {
  counts: AdminCounts | null;
  status: CharlaStreamStatus;
  tab: Tab;
  onTab: (tab: Tab) => void;
  projection: boolean;
  onProjection: () => void;
  onQr: () => void;
}

export function Header({ counts, status, tab, onTab, projection, onProjection, onQr }: Props) {
  const clock = useClock();
  const [monitorBase, setBase] = useState(getMonitorBase);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  function openSettings() {
    setDraft(monitorBase);
    setEditing((v) => !v);
  }

  function saveBase(event: FormEvent) {
    event.preventDefault();
    setMonitorBase(draft);
    setBase(getMonitorBase());
    setEditing(false);
  }

  return (
    <header className={styles.header}>
      <div className={styles.headerLeft}>
        <img src="/charla/logo.png" alt="IA Revolutions" className={styles.logo} />
        <span className={styles.vrule} />
        <div className={styles.brand}>
          <span className={styles.brandTitle}>PANEL DEL PRESENTADOR</span>
          <span className={styles.brandSub}>Agentic Engineering · vie 23 oct</span>
        </div>
      </div>

      <nav className={styles.tabs} aria-label="Secciones">
        <button
          type="button"
          className={styles.tab}
          aria-pressed={tab === "sala"}
          onClick={() => onTab("sala")}
          data-testid="pres-tab-sala"
        >
          SALA
        </button>
        <button
          type="button"
          className={styles.tab}
          aria-pressed={tab === "ranking"}
          onClick={() => onTab("ranking")}
          data-testid="pres-tab-ranking"
        >
          RANKING
        </button>
        {projection
          ? null
          : MONITOR_PAGES.map(({ label, page }) => (
              <a
                key={page}
                className={styles.tab}
                href={`${monitorBase}/${page}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                {label}↗
              </a>
            ))}
        {projection ? null : (
          <div className={styles.settingsWrap}>
            <button
              type="button"
              className={styles.iconBtn}
              onClick={openSettings}
              aria-expanded={editing}
              aria-label="Configurar el monitor de agentes"
              title="Configurar el monitor de agentes"
            >
              <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
                <circle cx="7" cy="7" r="2.2" fill="none" stroke="currentColor" strokeWidth="1.4" />
                <path
                  d="M7 1v2M7 11v2M1 7h2M11 7h2M2.8 2.8l1.4 1.4M9.8 9.8l1.4 1.4M2.8 11.2l1.4-1.4M9.8 4.2l1.4-1.4"
                  stroke="currentColor"
                  strokeWidth="1.4"
                />
              </svg>
            </button>
            {editing ? (
              <form
                className={styles.popover}
                onSubmit={saveBase}
                onKeyDown={(e) => {
                  if (e.key === "Escape") setEditing(false);
                }}
              >
                <label className="c-label" htmlFor="pres-monitor-base">
                  URL del monitor de agentes
                </label>
                <input
                  id="pres-monitor-base"
                  className={`c-fld ${styles.smallFld}`}
                  value={draft}
                  autoFocus
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder="http://localhost:4800"
                />
                <button type="submit" className={styles.miniBtn}>
                  GUARDAR
                </button>
              </form>
            ) : null}
          </div>
        )}
      </nav>

      <div className={styles.headerRight}>
        <div className={styles.headStat}>
          <span className={styles.headStatLabel}>REGISTRADOS</span>
          <span className={styles.headStatValue} data-testid="pres-registered">
            {counts?.registered ?? "—"}
          </span>
        </div>
        {projection ? null : (
          <div className={styles.headStat}>
            <span className={styles.headStatLabel}>VERIFICADOS</span>
            <span className={styles.headStatValue}>{counts?.verified ?? "—"}</span>
          </div>
        )}
        <div className={styles.headStat}>
          <span className={styles.headStatLabel}>HORA</span>
          <span className={styles.headStatValue}>{clock}</span>
        </div>
        <span className={styles.liveBadge} data-status={status} data-testid="pres-live" role="status">
          <span className={`${styles.liveDot} ${status === "live" ? "live" : ""}`} />
          {STATUS_LABEL[status]}
        </span>
        <button
          type="button"
          className={styles.iconBtn}
          onClick={onQr}
          title="Mostrar el QR (Q)"
          data-testid="pres-qr-toggle"
        >
          QR
        </button>
        <button
          type="button"
          className={styles.iconBtn}
          aria-pressed={projection}
          onClick={onProjection}
          title="Modo proyección (P)"
          data-testid="pres-projection-toggle"
        >
          {projection ? "SALIR" : "PROYECTAR"}
        </button>
      </div>
    </header>
  );
}
