"use client";

/**
 * /charla/ entry (CONTRACT §0, §5.1–§5.3). Step 1 asks for a username and an email; step 2
 * waits for the attendee to tap the button in the email and then enters the Sala on its own.
 * Ported from Registro.dc.html: split screen on desktop, a frosted bottom sheet at ≤ 760 px.
 */

import { useRouter } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api";
import { charlaApi, OFFLINE_MESSAGE } from "@/lib/charla/api";
import {
  clearPending,
  clearToken,
  getPending,
  getToken,
  type PendingInfo,
  setPending,
  setToken,
} from "@/lib/charla/session";
import type { UsernameCheck } from "@/lib/charla/types";
import { cleanUsername, emailError, usernameError } from "@/lib/charla/validate";

import styles from "./Registro.module.css";

/** Shows "Al continuar aceptas la política de datos." below the button. */
const SHOW_DATA_NOTICE = true;

const SALA = "/charla/sala/";
const CHECK_DEBOUNCE_MS = 400;
const POLL_MS = 2000;
const RESEND_S = 30;
/** How long "¡Listo, …!" stays before the Sala opens. */
const ENTER_DELAY_MS = 1200;
const TAKEN = "Ese nombre ya está en uso. Prueba con otro.";

type Step = "boot" | "form" | "sent" | "done";

interface Checked {
  u: string;
  result: UsernameCheck;
}

interface Hint {
  tone: "ok" | "error";
  text: string;
  suggestion?: string | null;
}

function failure(err: unknown): { status: number; message: string } {
  if (err instanceof ApiError) return { status: err.status, message: err.detail || OFFLINE_MESSAGE };
  return { status: 0, message: OFFLINE_MESSAGE };
}

/** A 409 detail names a free alternative: "…por ejemplo «José P2»." */
function suggestionIn(message: string): string | null {
  return /«([^»]+)»/.exec(message)?.[1] ?? null;
}

export function Registro() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("boot");
  const [paused, setPaused] = useState(false);

  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [tried, setTried] = useState(false);
  const [emailTouched, setEmailTouched] = useState(false);
  const [emailServerError, setEmailServerError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  /** The username (and valid email) the user stopped typing at, after the debounce. */
  const [query, setQuery] = useState<{ u: string; email?: string }>({ u: "" });
  const [checked, setChecked] = useState<Checked | null>(null);

  const [sent, setSent] = useState<PendingInfo | null>(null);
  const [cooldownS, setCooldownS] = useState(RESEND_S);
  const [now, setNow] = useState(() => Date.now());
  const [resending, setResending] = useState(false);
  const [resendError, setResendError] = useState<string | null>(null);
  const [doneName, setDoneName] = useState("");

  /** The live pending secret; a resend replaces it while polling runs. */
  const pendingRef = useRef<PendingInfo | null>(null);
  const enterTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const cleanU = cleanUsername(username);
  const nameProblem = usernameError(cleanU);
  const mail = email.trim();
  const emailProblem = emailError(mail);
  const emailForCheck = emailProblem ? undefined : mail;

  const enter = useCallback(
    (token: string, name: string, delayMs: number) => {
      setToken(token);
      clearPending();
      pendingRef.current = null;
      setDoneName(name);
      setStep("done");
      clearTimeout(enterTimer.current);
      enterTimer.current = setTimeout(() => router.replace(SALA), delayMs);
    },
    [router],
  );

  const backToForm = useCallback((message: string | null) => {
    clearPending();
    pendingRef.current = null;
    setSent(null);
    setFormError(message);
    setStep("form");
  }, []);

  useEffect(() => () => clearTimeout(enterTimer.current), []);

  // On load: a working session goes straight to the Sala; a pending registration resumes step 2.
  useEffect(() => {
    let live = true;
    void (async () => {
      const token = getToken();
      if (token) {
        try {
          await charlaApi.me(token);
          if (live) router.replace(SALA);
          return;
        } catch (err) {
          if (failure(err).status === 401) clearToken();
        }
      }
      if (!live) return;
      const pending = getPending();
      if (pending) {
        pendingRef.current = pending;
        setSent(pending);
        setUsername(pending.username);
        setEmail(pending.email);
        setNow(Date.now());
        setStep("sent");
      } else {
        setStep("form");
      }
    })();
    return () => {
      live = false;
    };
  }, [router]);

  // Debounce: check only once the user pauses typing.
  useEffect(() => {
    const timer = setTimeout(() => setQuery({ u: cleanU, email: emailForCheck }), CHECK_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [cleanU, emailForCheck]);

  // Live availability check; the client rules answer first, the server re-checks on submit.
  useEffect(() => {
    if (step !== "form" || !query.u || usernameError(query.u)) return;
    let live = true;
    charlaApi.checkUsername(query.u, query.email).then(
      (result) => {
        if (live) setChecked({ u: query.u, result });
      },
      () => undefined, // offline: submit will tell
    );
    return () => {
      live = false;
    };
  }, [step, query.u, query.email]);

  // Step 2: poll every 2 s, and right away whenever the page comes back into view.
  useEffect(() => {
    if (step !== "sent") return;
    let stopped = false;
    let inFlight = false;
    const poll = async () => {
      const current = pendingRef.current;
      if (stopped || inFlight || !current) return;
      inFlight = true;
      try {
        const res = await charlaApi.status(current.pending);
        if (!stopped && res.status === "in") {
          stopped = true;
          enter(res.token, res.username, ENTER_DELAY_MS);
        }
      } catch (err) {
        const { status, message } = failure(err);
        // A resend replaces the pending secret; only the current one's 404 counts.
        if (!stopped && status === 404 && pendingRef.current?.pending === current.pending) {
          stopped = true;
          backToForm(message);
        }
      } finally {
        inFlight = false;
      }
    };
    const onVisible = () => {
      if (document.visibilityState === "visible") void poll();
    };
    void poll();
    const timer = setInterval(() => void poll(), POLL_MS);
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onVisible);
    return () => {
      stopped = true;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("online", onVisible);
    };
  }, [step, enter, backToForm]);

  // Resend countdown tick.
  useEffect(() => {
    if (step !== "sent") return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [step]);

  async function send(name: string, address: string) {
    const res = await charlaApi.register(name, address);
    if (res.status === "in") {
      // Verification is off: the session comes back right away.
      enter(res.token, res.username, 0);
      return;
    }
    const info: PendingInfo = { pending: res.pending, email: res.email, username: res.username, sentAt: Date.now() };
    setPending(info);
    pendingRef.current = info;
    setSent(info);
    setCooldownS(res.resend_in_s > 0 ? res.resend_in_s : RESEND_S);
    setNow(info.sentAt);
    setResendError(null);
    setStep("sent");
  }

  function showSendError(err: unknown, name: string) {
    const { status, message } = failure(err);
    if (status === 409) {
      setChecked({ u: name, result: { valid: true, available: false, message, suggestion: suggestionIn(message) } });
    } else if (status === 400 && /correo/i.test(message)) {
      setEmailServerError(message);
    } else if (status === 400) {
      setChecked({ u: name, result: { valid: false, available: false, message, suggestion: null } });
    } else {
      setFormError(message);
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setTried(true);
    setFormError(null);
    if (nameProblem || emailProblem) return;
    setBusy(true);
    try {
      await send(cleanU, mail);
    } catch (err) {
      showSendError(err, cleanU);
    } finally {
      setBusy(false);
    }
  }

  const resendLeft = sent ? Math.max(0, Math.ceil((sent.sentAt + cooldownS * 1000 - now) / 1000)) : 0;

  async function onResend() {
    const current = pendingRef.current;
    if (!current || resending || resendLeft > 0) return;
    setResending(true);
    setResendError(null);
    try {
      await send(current.username, current.email);
    } catch (err) {
      const { status, message } = failure(err);
      if (status === 409 || status === 400) {
        backToForm(null);
        showSendError(err, cleanUsername(current.username));
      } else {
        setResendError(message);
      }
    } finally {
      setResending(false);
    }
  }

  // Username feedback: client rules once the user pauses (or on submit), then the server's answer.
  let hint: Hint | null = null;
  if (nameProblem) {
    if (tried || (cleanU !== "" && query.u === cleanU)) hint = { tone: "error", text: nameProblem };
  } else if (checked?.u === cleanU) {
    const r = checked.result;
    hint =
      r.valid && r.available
        ? { tone: "ok", text: "✓ Disponible" }
        : { tone: "error", text: r.message ?? TAKEN, suggestion: r.suggestion };
  }
  const suggestion = hint?.suggestion ?? null;
  const emailHint = emailServerError ?? (tried || (emailTouched && mail !== "") ? emailProblem : null);

  return (
    <div className={styles.reg}>
      <div className={`${styles.media} ${paused ? styles.paused : ""}`}>
        <div className={`${styles.glowA} anim`} aria-hidden="true" />
        <div className={`${styles.glowB} anim`} aria-hidden="true" />
        <div className={`${styles.glowC} anim`} aria-hidden="true" />
        <div className={`${styles.orbA} anim`} aria-hidden="true" />
        <div className={`${styles.orbB} anim`} aria-hidden="true" />
        <div className={`${styles.orbC} anim`} aria-hidden="true" />
        <svg className={styles.circuit} width="100%" height="100%" aria-hidden="true">
          <path d="M0 120 H260 L290 150 H620 M0 220 H180 L210 250 H420" />
          <path d="M60 0 V90 L90 120 M120 0 V70" />
        </svg>
        <div className={styles.shade} aria-hidden="true" />

        <a href="/charla/" className={styles.logo}>
          <img src="/charla/logo.png" alt="IA Revolutions" />
        </a>

        <div className={styles.copy}>
          <span className={styles.eyebrow}>CHARLA EN VIVO · AGENTIC ENGINEERING</span>
          <h2 className={`holo ${styles.hl}`}>Un equipo de agentes, en vivo.</h2>
          <p className={styles.sub}>
            Responde quices desde tu celular, mira cómo evoluciona la sala y compite por el primer lugar.
          </p>
          <div className={styles.chips}>
            <span className="c-chip">7 PREGUNTAS</span>
            <span className="c-chip">RANKING</span>
            <span className="c-chip">SIN CONTRASEÑA</span>
          </div>
        </div>

        <button
          type="button"
          className={styles.pause}
          onClick={() => setPaused((p) => !p)}
          aria-label={paused ? "Reproducir animación de fondo" : "Pausar animación de fondo"}
          title={paused ? "Reproducir animación de fondo" : "Pausar animación de fondo"}
        >
          {paused ? (
            <svg width="12" height="12" aria-hidden="true">
              <path d="M2.5 1 L10.5 6 L2.5 11 Z" fill="currentColor" />
            </svg>
          ) : (
            <svg width="12" height="12" aria-hidden="true">
              <rect x="2" y="1" width="2.6" height="10" fill="currentColor" />
              <rect x="7.4" y="1" width="2.6" height="10" fill="currentColor" />
            </svg>
          )}
        </button>
      </div>

      <div className={styles.panel}>
        <div className={styles.inner}>
          {step === "boot" && (
            <p className={styles.lead} aria-busy="true">
              Cargando…
            </p>
          )}

          {step === "form" && (
            <form className={`rise ${styles.stack}`} onSubmit={onSubmit} noValidate>
              <div className={styles.head}>
                <span className="c-kicker">01 · ENTRADA</span>
                <h1 className={styles.title}>Entra a la sala</h1>
                <p className={styles.lead}>Dos datos y un botón en tu correo. Sin contraseña.</p>
              </div>

              <div className={styles.field}>
                <label htmlFor="charla-username" className="c-label">
                  NOMBRE DE USUARIO
                </label>
                <input
                  id="charla-username"
                  data-testid="charla-username"
                  className="c-fld"
                  type="text"
                  autoComplete="nickname"
                  enterKeyHint="next"
                  placeholder="Así aparecerás en el ranking"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  aria-invalid={hint?.tone === "error"}
                  aria-describedby="charla-username-hint"
                />
                <div
                  id="charla-username-hint"
                  data-testid="charla-username-hint"
                  data-tone={hint?.tone}
                  className={styles.hint}
                  aria-live="polite"
                >
                  {hint && (
                    <>
                      <span className={hint.tone === "ok" ? styles.ok : styles.bad}>{hint.text}</span>
                      {suggestion && (
                        <button type="button" className={styles.suggest} onClick={() => setUsername(suggestion)}>
                          Usar «{suggestion}»
                        </button>
                      )}
                    </>
                  )}
                </div>
              </div>

              <div className={styles.field}>
                <label htmlFor="charla-email" className="c-label">
                  CORREO ELECTRÓNICO
                </label>
                <input
                  id="charla-email"
                  data-testid="charla-email"
                  className="c-fld"
                  type="email"
                  inputMode="email"
                  autoComplete="email"
                  autoCapitalize="none"
                  spellCheck={false}
                  enterKeyHint="go"
                  placeholder="tu@empresa.com"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    setEmailServerError(null);
                  }}
                  onBlur={() => setEmailTouched(true)}
                  aria-invalid={emailHint ? true : undefined}
                  aria-describedby={emailHint ? "charla-email-error" : undefined}
                />
                {emailHint && (
                  <span id="charla-email-error" data-testid="charla-email-error" className="c-err">
                    {emailHint}
                  </span>
                )}
              </div>

              <button type="submit" className="c-btn" data-testid="charla-submit" disabled={busy}>
                {busy ? "ENVIANDO…" : "ENTRAR A LA SALA"}
                {!busy && (
                  <svg width="16" height="10" aria-hidden="true">
                    <path d="M0 5 H14 M10 1.5 L14 5 L10 8.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
                  </svg>
                )}
              </button>

              {formError && (
                <p role="alert" data-testid="charla-form-error" className={`c-err ${styles.formError}`}>
                  {formError}
                </p>
              )}

              {SHOW_DATA_NOTICE && (
                <p className={styles.notice}>
                  <svg width="13" height="13" aria-hidden="true">
                    <rect x="2" y="6" width="9" height="6" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.3" />
                    <path d="M4 6 V4 A2.5 2.5 0 0 1 9 4 V6" fill="none" stroke="currentColor" strokeWidth="1.3" />
                  </svg>
                  <span>
                    Al continuar aceptas la <a href="/charla/datos/">política de datos</a>.
                  </span>
                </p>
              )}
            </form>
          )}

          {step === "sent" && sent && (
            <div className={`rise ${styles.stack}`} data-testid="charla-waiting">
              <div className={styles.mail} aria-hidden="true">
                <span className={`${styles.ring} pulse`} />
                <svg width="38" height="30">
                  <rect x="1.5" y="1.5" width="35" height="27" rx="4" fill="none" stroke="currentColor" strokeWidth="1.8" />
                  <path d="M3 5 L19 17 L35 5" fill="none" stroke="currentColor" strokeWidth="1.8" />
                </svg>
              </div>
              <div className={styles.head}>
                <span className="c-kicker">02 · REVISA TU CORREO</span>
                <h1 className={styles.title}>Te enviamos el enlace</h1>
                <p className={styles.body}>
                  Toca el botón ENTRAR A LA SALA del correo que enviamos a{" "}
                  <span className={styles.strong}>{sent.email}</span>. Esta pantalla entra sola.
                </p>
              </div>
              <div className={styles.actions}>
                <button
                  type="button"
                  data-testid="charla-resend"
                  className={`c-btn-ghost ${resendLeft === 0 && !resending ? styles.resendReady : ""}`}
                  onClick={onResend}
                  disabled={resendLeft > 0 || resending}
                >
                  {resending ? "REENVIANDO…" : resendLeft > 0 ? `REENVIAR EN ${resendLeft} s` : "REENVIAR ENLACE"}
                </button>
                {resendError && (
                  <span role="alert" className="c-err">
                    {resendError}
                  </span>
                )}
                <button type="button" className="c-btn-link" onClick={() => backToForm(null)}>
                  Cambiar correo
                </button>
              </div>
              <span className={styles.tip}>¿No llega? Revisa spam o promociones.</span>
            </div>
          )}

          {step === "done" && (
            <div className={`pop ${styles.stack}`} role="status" data-testid="charla-done">
              <div className={styles.mail} aria-hidden="true">
                <span className={styles.ring} />
                <svg width="30" height="24">
                  <path d="M3 12.5 L11 20 L27 4" fill="none" stroke="currentColor" strokeWidth="2.4" />
                </svg>
              </div>
              <div className={styles.head}>
                <h1 className={styles.title}>¡Listo, {doneName}!</h1>
                <p className={styles.lead}>Entrando a la sala…</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
