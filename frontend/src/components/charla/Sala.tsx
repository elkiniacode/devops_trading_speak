"use client";

import { useRouter } from "next/navigation";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api";
import { charlaApi } from "@/lib/charla/api";
import { clearToken, getToken } from "@/lib/charla/session";
import { useCharlaStream } from "@/lib/charla/stream";
import type { AnswerBody, AttendeeView, Me, MyAnswer, PhoneBody, PhoneStatus } from "@/lib/charla/types";
import { viewFor } from "@/lib/charla/views";

import s from "./Sala.module.css";
import { AnsweredView } from "./sala/AnsweredView";
import { EndView } from "./sala/EndView";
import { OpenView } from "./sala/OpenView";
import { PhoneView } from "./sala/PhoneView";
import { QuestionView } from "./sala/QuestionView";
import { ResultView } from "./sala/ResultView";
import { SalaHeader } from "./sala/SalaHeader";
import { WaitView } from "./sala/WaitView";

const TOAST_MS = 3500;
const OFFLINE = "Sin conexión. Revisa tu internet e intenta de nuevo.";

const isExpired = (e: unknown) => e instanceof ApiError && e.status === 401;
const messageOf = (e: unknown) => (e instanceof ApiError && e.detail ? e.detail : OFFLINE);

/** The attendee's phone during the talk (CONTRACT §5.5–§5.8, §6.1, §9.2). */
export function Sala() {
  const router = useRouter();
  const [token, setTokenState] = useState<string | null>(null);
  const leaving = useRef(false);

  /** The session is gone: forget it and go back to registration. */
  const leave = useCallback(() => {
    if (leaving.current) return;
    leaving.current = true;
    clearToken();
    router.replace("/charla/");
  }, [router]);

  // localStorage only exists in the browser, so read the session after mount.
  useEffect(() => {
    const saved = getToken();
    if (saved) {
      setTokenState(saved);
    } else if (!leaving.current) {
      leaving.current = true;
      router.replace("/charla/");
    }
  }, [router]);

  const poll = useCallback(async (): Promise<AttendeeView> => {
    try {
      return await charlaApi.me(token ?? "");
    } catch (e) {
      if (isExpired(e)) leave();
      throw e;
    }
  }, [token, leave]);

  const { data, status, receivedAt } = useCharlaStream<AttendeeView>(
    token ? charlaApi.streamUrl(token) : null,
    poll,
  );
  const state = data?.state ?? null;
  const serverMe = data?.me ?? null;

  // A view without "me" means the session no longer exists (e.g. the presenter reset the room).
  useEffect(() => {
    if (data && data.me === null) leave();
  }, [data, leave]);

  // Optimistic local state, until the stream confirms it.
  const [pending, setPending] = useState<MyAnswer | null>(null);
  const [phoneLocal, setPhoneLocal] = useState<PhoneStatus | null>(null);
  const [draft, setDraft] = useState("");
  const [toast, setToast] = useState<string | null>(null);

  // Drop the optimistic answer once the server has it, or when the step goes back to idle.
  const confirmed = serverMe?.answer?.step ?? null;
  const idle = state?.phase === "idle";
  useEffect(() => {
    if (idle) setPending(null);
    else if (confirmed !== null) setPending((p) => (p && p.step === confirmed ? null : p));
  }, [idle, confirmed]);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), TOAST_MS);
    return () => clearTimeout(id);
  }, [toast]);

  const answer = useCallback(
    async (body: AnswerBody) => {
      if (!token) return;
      setPending({
        step: body.step,
        choice: "choice" in body ? body.choice : null,
        text: "text" in body ? body.text : null,
      });
      try {
        await charlaApi.answer(token, body);
      } catch (e) {
        if (isExpired(e)) return leave();
        setPending(null);
        setToast(messageOf(e));
      }
    },
    [token, leave],
  );

  const sendPhone = useCallback(
    async (body: PhoneBody): Promise<string | null> => {
      if (!token) return null;
      try {
        await charlaApi.phone(token, body);
        setPhoneLocal("skip" in body ? "skipped" : "given");
        return null;
      } catch (e) {
        if (isExpired(e)) {
          leave();
          return null;
        }
        return messageOf(e);
      }
    },
    [token, leave],
  );

  const me: Me | null = serverMe && {
    ...serverMe,
    answer: serverMe.answer ?? (pending && state && pending.step === state.step ? pending : null),
    phone_status: serverMe.phone_status === "none" && phoneLocal ? phoneLocal : serverMe.phone_status,
  };
  const view = state && me ? viewFor(state, me) : null;

  function renderView() {
    if (!state || !me) return null;
    switch (view) {
      case "wait":
        return <WaitView state={state} />;
      case "question":
        return (
          <QuestionView state={state} receivedAt={receivedAt} onPick={(choice) => void answer({ step: state.step, choice })} />
        );
      case "answered":
        return <AnsweredView state={state} answer={me.answer} />;
      case "result":
        return <ResultView state={state} me={me} />;
      case "open":
        return (
          <OpenView
            state={state}
            receivedAt={receivedAt}
            draft={draft}
            onDraft={setDraft}
            onSend={(text) => void answer({ step: state.step, text })}
          />
        );
      case "phone":
        return <PhoneView onSubmit={sendPhone} />;
      case "end":
        return <EndView me={me} />;
      default:
        return null;
    }
  }

  return (
    <div className={s.screen} data-testid="sala" data-view={view ?? "loading"}>
      <div className={s.glowA} aria-hidden="true" />
      <div className={s.glowB} aria-hidden="true" />
      <SalaHeader me={me} />
      {data && status !== "live" && (
        <div className={s.pill} role="status" data-testid="sala-reconnecting">
          <span className={s.pillDot} aria-hidden="true" />
          Reconectando…
        </div>
      )}
      <main className={s.main}>
        {view && state ? (
          <Fragment key={`${view}-${state.step}`}>{renderView()}</Fragment>
        ) : (
          <div className={s.loading}>
            <div className={s.beacon} aria-hidden="true">
              <span className={s.ring} />
              <span className={s.dot} />
            </div>
            <span>CONECTANDO A LA SALA…</span>
          </div>
        )}
      </main>
      {toast && (
        <div className={s.toast} role="alert" data-testid="sala-toast">
          {toast}
        </div>
      )}
    </div>
  );
}
