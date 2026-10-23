"use client";

/**
 * Presenter panel (/charla/presentador/): key gate in front of the live control room.
 * The key comes from localStorage or a one-off `#key=` in the URL; any 401 sends the
 * presenter back to the gate.
 */
import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/lib/api";
import { adminApi } from "@/lib/charla/api";
import { clearAdminKey, getAdminKey, setAdminKey } from "@/lib/charla/session";

import { KeyGate } from "./presenter/KeyGate";
import { PresenterPanel } from "./presenter/PresenterPanel";

export const WRONG_KEY = "Clave de presentador incorrecta.";

/** `#key=abc` -> "abc"; anything else -> null. */
export function keyFromHash(hash: string): string | null {
  const params = new URLSearchParams(hash.replace(/^#/, ""));
  const key = params.get("key")?.trim();
  return key ? key : null;
}

/** Check a key against the server: null when usable, else the Spanish reason. */
async function verifyKey(key: string): Promise<string | null> {
  try {
    return (await adminApi(key).check()) ? null : WRONG_KEY;
  } catch (error) {
    // Offline or a server hiccup: keep the key, the stream retries on its own.
    if (error instanceof ApiError && error.status === 503) {
      return error.detail || "El servidor no tiene clave de presentador configurada.";
    }
    return null;
  }
}

export function Presentador() {
  const [ready, setReady] = useState(false);
  const [key, setKey] = useState<string | null>(null);
  const [gateError, setGateError] = useState<string | null>(null);

  const lock = useCallback((message: string) => {
    clearAdminKey();
    setKey(null);
    setGateError(message);
  }, []);

  useEffect(() => {
    let stored = keyFromHash(window.location.hash);
    if (stored) {
      setAdminKey(stored);
      // Don't leave the key in the address bar (or in a screenshot of it).
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    } else {
      stored = getAdminKey();
    }
    setKey(stored);
    setReady(true);
    if (!stored) return;
    let alive = true;
    void verifyKey(stored).then((problem) => {
      if (alive && problem) lock(problem);
    });
    return () => {
      alive = false;
    };
  }, [lock]);

  const submit = useCallback(async (candidate: string) => {
    const problem = await verifyKey(candidate);
    if (problem) {
      setGateError(problem);
      return;
    }
    setAdminKey(candidate);
    setGateError(null);
    setKey(candidate);
  }, []);

  if (!ready) return null;
  if (!key) return <KeyGate error={gateError} onSubmit={submit} />;
  return <PresenterPanel adminKey={key} onUnauthorized={() => lock(WRONG_KEY)} />;
}

export default Presentador;
