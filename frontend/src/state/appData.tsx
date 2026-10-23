"use client";

import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { Health, Portfolio, Snapshot, WatchlistItem } from "@/lib/types";

/** P&L chart refresh cadence, matching the backend's snapshot interval (CONTRACTS R29). */
export const HISTORY_POLL_MS = 30_000;

/** A watchlist click. `seq` > 0 means the user picked it, so the trade bar should pre-fill. */
export interface Selection {
  ticker: string;
  seq: number;
}

export interface AppData {
  portfolio: Portfolio | null;
  watchlist: WatchlistItem[] | null;
  snapshots: Snapshot[] | null;
  health: Health | null;
  /** Set when the initial load failed (e.g. the server isn't up yet). */
  loadError: string | null;
  selection: Selection | null;
  selectTicker: (ticker: string) => void;
  /** Refetch portfolio, watchlist and history after any mutation (CONTRACTS R29). */
  refreshAll: () => Promise<void>;
  setPortfolio: (portfolio: Portfolio) => void;
  setWatchlist: (items: WatchlistItem[]) => void;
}

const AppDataContext = createContext<AppData | null>(null);

function message(err: unknown): string {
  return err instanceof ApiError ? err.detail : "Something went wrong loading your data.";
}

/** Loads the REST state on mount, polls the P&L history and owns the selected ticker. */
export function AppDataProvider({ children }: { children: ReactNode }) {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistItem[] | null>(null);
  const [snapshots, setSnapshots] = useState<Snapshot[] | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);

  const loadHistory = useCallback(async () => {
    try {
      setSnapshots((await api.history()).snapshots);
    } catch {
      // keep the last good chart; the next poll retries
    }
  }, []);

  const refreshAll = useCallback(async () => {
    const results = await Promise.allSettled([
      api.portfolio().then(setPortfolio),
      api.watchlist().then((r) => setWatchlist(r.watchlist)),
      api.history().then((r) => setSnapshots(r.snapshots)),
      api.health().then(setHealth),
    ]);
    const failed = results.find((r): r is PromiseRejectedResult => r.status === "rejected");
    setLoadError(failed ? message(failed.reason) : null);
  }, []);

  useEffect(() => {
    void refreshAll();
    const timer = setInterval(loadHistory, HISTORY_POLL_MS);
    return () => clearInterval(timer);
  }, [refreshAll, loadHistory]);

  // Default the chart to the first watchlist ticker, and fall back to it when the selected
  // ticker is neither watched nor held any more. Neither case touches the trade bar (seq 0).
  useEffect(() => {
    if (!watchlist) return;
    const known =
      selection &&
      (watchlist.some((w) => w.ticker === selection.ticker) ||
        portfolio?.positions.some((p) => p.ticker === selection.ticker));
    if (known) return;
    const next = watchlist[0]?.ticker;
    if (next && next !== selection?.ticker) setSelection({ ticker: next, seq: 0 });
  }, [selection, watchlist, portfolio]);

  const selectTicker = useCallback((ticker: string) => {
    setSelection((prev) => ({ ticker, seq: (prev?.seq ?? 0) + 1 }));
  }, []);

  const value = useMemo<AppData>(
    () => ({
      portfolio,
      watchlist,
      snapshots,
      health,
      loadError,
      selection,
      selectTicker,
      refreshAll,
      setPortfolio,
      setWatchlist,
    }),
    [portfolio, watchlist, snapshots, health, loadError, selection, selectTicker, refreshAll],
  );

  return <AppDataContext.Provider value={value}>{children}</AppDataContext.Provider>;
}

export function useAppData(): AppData {
  const value = useContext(AppDataContext);
  if (!value) throw new Error("useAppData must be used inside <AppDataProvider>");
  return value;
}
