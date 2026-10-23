"use client";

/**
 * /charla/entrar/#v=<link-token> (CONTRACT §0, §5.4): the email button lands here. It verifies
 * the link, stores this browser's session and opens the Sala. The tab that registered (maybe on
 * another device) gets approved too and enters on its own.
 */

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api";
import { charlaApi } from "@/lib/charla/api";
import { clearPending, setToken } from "@/lib/charla/session";
import type { VerifyResponse } from "@/lib/charla/types";

import styles from "./Entrar.module.css";

const SALA = "/charla/sala/";
const ENTER_DELAY_MS = 1500;
const INVALID = "Este enlace expiró o no es válido. Pide uno nuevo.";
const OFFLINE = "Sin conexión. Revisa tu internet e intenta de nuevo.";

type State = { kind: "checking" } | { kind: "ok"; username: string } | { kind: "error"; message: string };

/** Reads `v` from the hash once, then removes the hash so the token doesn't linger in history. */
function takeLinkToken(): string | null {
  const hash = window.location.hash;
  if (!hash) return null;
  window.history.replaceState(null, "", window.location.pathname + window.location.search);
  return new URLSearchParams(hash.slice(1)).get("v") || null;
}

export function Entrar() {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: "checking" });
  // Refs survive React's dev double-mount: the hash is read and verified only once.
  const request = useRef<Promise<VerifyResponse> | null | undefined>(undefined);

  useEffect(() => {
    if (request.current === undefined) {
      const v = takeLinkToken();
      request.current = v ? charlaApi.verify(v) : null;
    }
    const pending = request.current;
    if (!pending) {
      setState({ kind: "error", message: INVALID });
      return;
    }
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    pending.then(
      (res) => {
        if (!live) return;
        setToken(res.token);
        clearPending();
        setState({ kind: "ok", username: res.username });
        timer = setTimeout(() => router.replace(SALA), ENTER_DELAY_MS);
      },
      (err: unknown) => {
        if (!live) return;
        setState({ kind: "error", message: err instanceof ApiError ? err.detail || INVALID : OFFLINE });
      },
    );
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [router]);

  return (
    <main className={styles.page} data-testid="charla-entrar" data-state={state.kind}>
      <div className={`${styles.glowA} anim`} aria-hidden="true" />
      <div className={`${styles.glowB} anim`} aria-hidden="true" />

      <div className={`rise ${styles.card}`}>
        <a href="/charla/" className={styles.logo}>
          <img src="/charla/logo.png" alt="IA Revolutions" />
        </a>

        <span className="c-kicker">ENLACE DE ACCESO</span>

        {state.kind === "checking" && (
          <div className={styles.block} role="status">
            <span className={styles.badge} aria-hidden="true">
              <span className={`${styles.ring} pulse`} />
            </span>
            <h1 className={`holo ${styles.title}`}>Verificando…</h1>
          </div>
        )}

        {state.kind === "ok" && (
          <div className={`pop ${styles.block}`} role="status">
            <span className={styles.badge} aria-hidden="true">
              <span className={styles.ring} />
              <svg width="30" height="24">
                <path d="M3 12.5 L11 20 L27 4" fill="none" stroke="currentColor" strokeWidth="2.4" />
              </svg>
            </span>
            <h1 className={`holo ${styles.title}`}>¡Listo, {state.username}! Ya estás dentro.</h1>
            <p className={styles.body}>
              Si te registraste en otro navegador o dispositivo, ya puedes volver allí: entra solo.
            </p>
          </div>
        )}

        {state.kind === "error" && (
          <div className={styles.block} role="alert">
            <h1 className={`holo ${styles.title}`}>No pudimos entrar</h1>
            <p className={styles.error}>{state.message}</p>
            <a href="/charla/" className={`c-btn ${styles.cta}`}>
              Pedir un enlace nuevo
            </a>
          </div>
        )}
      </div>
    </main>
  );
}
