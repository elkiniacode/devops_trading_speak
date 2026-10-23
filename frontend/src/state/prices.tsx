"use client";

import { createContext, type ReactNode, useContext, useEffect, useState, useSyncExternalStore } from "react";

import { PRICE_STREAM_URL } from "@/lib/api";
import { connectPriceStream, type PriceState, PriceStore } from "@/lib/priceStore";

const PriceStoreContext = createContext<PriceStore | null>(null);

interface PriceProviderProps {
  children: ReactNode;
  /** Tests inject a pre-filled store. */
  store?: PriceStore;
  /** Open the SSE connection (off in tests). */
  connect?: boolean;
}

export function PriceProvider({ children, store, connect = true }: PriceProviderProps) {
  const [value] = useState(() => store ?? new PriceStore());
  useEffect(() => {
    if (!connect) return;
    return connectPriceStream(value, PRICE_STREAM_URL);
  }, [value, connect]);
  return <PriceStoreContext.Provider value={value}>{children}</PriceStoreContext.Provider>;
}

/** Live prices, per-ticker buffers and connection status; re-renders on every SSE event. */
export function usePrices(): PriceState {
  const store = useContext(PriceStoreContext);
  if (!store) throw new Error("usePrices must be used inside <PriceProvider>");
  return useSyncExternalStore(store.subscribe, store.getState, store.getServerState);
}
