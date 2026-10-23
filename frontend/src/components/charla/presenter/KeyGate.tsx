"use client";

import { type FormEvent, useState } from "react";

import styles from "./presenter.module.css";

interface Props {
  error: string | null;
  onSubmit: (key: string) => Promise<void>;
}

/** Small centred form that asks for the presenter key. */
export function KeyGate({ error, onSubmit }: Props) {
  const [value, setValue] = useState("");
  const [checking, setChecking] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const key = value.trim();
    if (!key || checking) return;
    setChecking(true);
    try {
      await onSubmit(key);
    } finally {
      setChecking(false);
    }
  }

  return (
    <main className={styles.gate}>
      <form className={`${styles.gateCard} c-card rise`} onSubmit={submit} data-testid="pres-gate">
        <img src="/charla/logo.png" alt="IA Revolutions" className={styles.gateLogo} />
        <label className="c-label" htmlFor="pres-key">
          Clave del presentador
        </label>
        <input
          id="pres-key"
          className="c-fld"
          type="password"
          autoComplete="current-password"
          autoFocus
          value={value}
          onChange={(e) => setValue(e.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "pres-key-error" : undefined}
          data-testid="pres-key-input"
        />
        {error ? (
          <p id="pres-key-error" className="c-err" role="alert">
            {error}
          </p>
        ) : null}
        <button type="submit" className="c-btn" disabled={!value.trim() || checking}>
          {checking ? "VERIFICANDO…" : "ENTRAR"}
        </button>
      </form>
    </main>
  );
}
