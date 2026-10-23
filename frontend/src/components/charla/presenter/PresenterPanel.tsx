"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError } from "@/lib/api";
import { adminApi } from "@/lib/charla/api";
import { useCharlaStream } from "@/lib/charla/stream";
import type { AdminView } from "@/lib/charla/types";

import { Header, type Tab } from "./Header";
import { useStageScale, useToast } from "./hooks";
import { type Action, controlsFor, isTypingTarget, shortcutFor } from "./logic";
import { QrOverlay } from "./Overlays";
import { ProjectionSala } from "./ProjectionSala";
import { ControlBar, QuestionBody, QuestionHead } from "./QuestionPanel";
import { Ranking } from "./Ranking";
import { ScriptColumn } from "./ScriptColumn";
import { SidePanel } from "./SidePanel";
import styles from "./presenter.module.css";

interface Props {
  adminKey: string;
  onUnauthorized: () => void;
}

/** The live control room: admin stream in, adminApi calls out, on a 1440×810 stage. */
export function PresenterPanel({ adminKey, onUnauthorized }: Props) {
  const api = useMemo(() => adminApi(adminKey), [adminKey]);
  const { data: view, status, receivedAt } = useCharlaStream<AdminView>(api.streamUrl);
  const [tab, setTab] = useState<Tab>("sala");
  const [projection, setProjection] = useState(false);
  const [qrOpen, setQrOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [toast, showToast] = useToast();
  const scale = useStageScale();

  /** Runs one admin call: 401 -> back to the gate, anything else -> a brief toast. */
  const run = useCallback(
    async (call: () => Promise<unknown>) => {
      setBusy(true);
      try {
        await call();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          onUnauthorized();
          return;
        }
        showToast(error instanceof ApiError && error.detail ? error.detail : "No se pudo completar la acción.");
      } finally {
        setBusy(false);
      }
    },
    [onUnauthorized, showToast],
  );

  const doAction = useCallback(
    (action: Action) => {
      if (!view || busy) return;
      const c = controlsFor(view.state, view.counts.answered);
      switch (action) {
        case "launch":
        case "phoneNow":
          if (c.launch.enabled) void run(c.launch.action === "phoneNow" ? api.phoneNow : api.launch);
          break;
        case "close":
          if (c.close.enabled) void run(api.close);
          break;
        case "reveal":
          if (c.reveal.enabled) void run(api.reveal);
          break;
        case "next":
          if (c.next.enabled) void run(api.next);
          break;
        case "resetStep":
          if (c.resetStep.enabled && window.confirm("¿Borrar las respuestas de esta pregunta y dejarla en espera?")) {
            void run(api.resetStep);
          }
          break;
      }
    },
    [view, busy, run, api],
  );

  const gotoStep = useCallback(
    (step: number) => {
      if (!view || busy || step === view.state.step) return;
      if (view.state.phase === "open") {
        if (!window.confirm(`La pregunta actual sigue abierta. ¿Cerrarla e ir al paso ${step + 1}?`)) return;
        void run(async () => {
          await api.close();
          await api.goto(step);
        });
        return;
      }
      void run(() => api.goto(step));
    },
    [view, busy, run, api],
  );

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.ctrlKey || e.metaKey || e.altKey || isTypingTarget(e.target)) return;
      const shortcut = shortcutFor(e.key);
      if (!shortcut) return;
      if (shortcut === "escape") {
        if (qrOpen) setQrOpen(false);
        else if (projection) setProjection(false);
        return;
      }
      e.preventDefault();
      if (shortcut === "projection") setProjection((p) => !p);
      else if (shortcut === "qr") setQrOpen((o) => !o);
      else doAction(shortcut);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [doAction, qrOpen, projection]);

  let content;
  if (!view) {
    content = (
      <div className={styles.connecting} data-testid="pres-connecting">
        {status === "offline" ? "Sin conexión con el servidor. Reintentando…" : "Conectando con la sala…"}
      </div>
    );
  } else if (tab === "ranking") {
    content = (
      <Ranking
        ranking={view.ranking}
        projection={projection}
        busy={busy}
        onToggleHide={(r) => void run(() => api.hide({ attendee_id: r.attendee_id, hidden: !r.hidden }))}
      />
    );
  } else if (projection) {
    content = <ProjectionSala view={view} receivedAt={receivedAt} />;
  } else {
    content = (
      <section className={styles.grid}>
        <ScriptColumn script={view.script} state={view.state} busy={busy} onGoto={gotoStep} />
        <main className={styles.center}>
          <QuestionHead view={view} receivedAt={receivedAt} />
          <QuestionBody view={view} />
          <ControlBar view={view} busy={busy} onAction={doAction} />
        </main>
        <SidePanel
          view={view}
          busy={busy}
          exportUrl={api.exportUrl}
          onHideQuote={(q) => void run(() => api.hide({ answer_id: q.answer_id, hidden: !q.hidden }))}
          onVerification={(on) => void run(() => api.verification(on))}
          onReclassify={() => void run(api.reclassify)}
          onResetAll={() => void run(api.reset)}
        />
      </section>
    );
  }

  return (
    <div className={styles.viewport}>
      <div
        className={styles.stage}
        style={{ transform: `translate(-50%, -50%) scale(${scale})` }}
        data-testid="pres-stage"
      >
        <div className={styles.screen} data-projection={projection ? "true" : "false"} data-testid="pres-screen">
          <Header
            counts={view?.counts ?? null}
            status={status}
            tab={tab}
            onTab={setTab}
            projection={projection}
            onProjection={() => setProjection((p) => !p)}
            onQr={() => setQrOpen((o) => !o)}
          />
          {content}
          {qrOpen ? <QrOverlay onClose={() => setQrOpen(false)} /> : null}
          {toast ? (
            <div className={styles.toast} role="status" data-testid="pres-toast">
              {toast}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
