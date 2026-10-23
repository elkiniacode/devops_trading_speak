"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const CLOCK_FORMAT: Intl.DateTimeFormatOptions = {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  timeZone: "America/Bogota",
};

/** Bogotá wall clock (es-CO), ticking every second. Empty until mounted. */
export function useClock(): string {
  const [text, setText] = useState("");
  useEffect(() => {
    const tick = () => setText(new Date().toLocaleTimeString("es-CO", CLOCK_FORMAT));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return text;
}

/** Re-renders every `ms` while `active`, for local countdowns. Returns performance.now(). */
export function useTicker(ms: number, active: boolean): number {
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    if (!active) return;
    setNow(performance.now());
    const id = setInterval(() => setNow(performance.now()), ms);
    return () => clearInterval(id);
  }, [ms, active]);
  return now;
}

/** One brief message at a time; a new one replaces the old and restarts the timer. */
export function useToast(durationMs = 3500): [string | null, (message: string) => void] {
  const [message, setMessage] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );
  const show = useCallback(
    (text: string) => {
      if (timer.current) clearTimeout(timer.current);
      setMessage(text);
      timer.current = setTimeout(() => setMessage(null), durationMs);
    },
    [durationMs],
  );
  return [message, show];
}

/** Fits a fixed 1440×810 stage into the window. */
export function useStageScale(width = 1440, height = 810): number {
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const fit = () => setScale(Math.min(window.innerWidth / width, window.innerHeight / height));
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, [width, height]);
  return scale;
}
