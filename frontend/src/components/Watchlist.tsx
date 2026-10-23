"use client";

import { type FormEvent, useState } from "react";

import { useFlash } from "@/hooks/useFlash";
import { formatPercent, formatPrice, pnlSign } from "@/lib/format";
import type { PricePoint } from "@/lib/priceStore";
import type { MarketMode, PriceMap, PriceUpdate, WatchlistItem } from "@/lib/types";

import { Panel } from "./Panel";
import { Sparkline } from "./Sparkline";
import { SIGN_TEXT } from "./tone";

/** Grid shared by the column headings and the rows so they line up. */
const COLUMNS = "grid grid-cols-[minmax(48px,1fr)_30px_58px_48px] items-center gap-x-1";
const STOCK_NAMES: Record<string, string> = { AAPL: "Apple", GOOGL: "Alphabet", MSFT: "Microsoft", AMZN: "Amazon", TSLA: "Tesla", NVDA: "Nvidia", META: "Meta", JPM: "JPMorgan", V: "Visa", NFLX: "Netflix", AMD: "AMD", INTC: "Intel", ORCL: "Oracle", PYPL: "PayPal", BAC: "Bank of America", GS: "Goldman Sachs", DIS: "Disney", WMT: "Walmart" };

interface WatchlistProps {
  items: WatchlistItem[] | null;
  prices: PriceMap;
  history: Record<string, PricePoint[]>;
  selectedTicker: string | null;
  mode: MarketMode | null;
  heldTickers?: Set<string>;
  onSelect: (ticker: string) => void;
  /** Resolve to an error message to show, or null on success. */
  onAdd: (ticker: string) => Promise<string | null>;
  onRemove: (ticker: string) => Promise<string | null>;
}

export function Watchlist({ items, prices, history, selectedTicker, mode, heldTickers, onSelect, onAdd, onRemove }: WatchlistProps) {
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const ticker = draft.trim().toUpperCase();
    if (!ticker || busy) return;
    setBusy(true);
    const failure = await onAdd(ticker);
    setBusy(false);
    setError(failure);
    if (!failure) setDraft("");
  }

  async function remove(ticker: string) {
    setError(await onRemove(ticker));
  }

  const changeHint = mode === "simulator" ? "Cambio desde el inicio de sesión" : "Cambio desde el cierre anterior";

  return (
    <Panel
      title="Lista de seguimiento"
      meta={items ? `${items.length} símbolos` : undefined}
      className="h-full"
      bodyClassName="flex flex-col"
    >
      <div className={`${COLUMNS} h-7 shrink-0 border-b border-line pr-7 pl-2 text-[9px] text-dim`}>
        <span>Símbolo</span>
        <span aria-hidden="true" />
        <span className="text-right">Último</span>
        <span className="text-right" title={changeHint}>
          Var. %
        </span>
      </div>

      <ul data-testid="watchlist" className="min-h-0 flex-1 overflow-y-auto">
        {items === null && <li className="px-3 py-4 text-[12px] text-dim">Cargando lista…</li>}
        {items?.length === 0 && (
          <li className="px-3 py-4 text-[12px] text-muted">La lista está vacía. Agrega un símbolo abajo.</li>
        )}
        {items?.map((item) => (
          <WatchlistRow
            key={item.ticker}
            ticker={item.ticker}
            quote={prices[item.ticker] ?? item.quote}
            points={history[item.ticker] ?? EMPTY_POINTS}
            selected={item.ticker === selectedTicker}
            held={heldTickers?.has(item.ticker)}
            changeHint={changeHint}
            onSelect={onSelect}
            onRemove={remove}
          />
        ))}
      </ul>

      <form onSubmit={submit} className="shrink-0 border-t border-line p-2.5">
        <div className="flex gap-2">
          <label htmlFor="watchlist-add" className="sr-only">
            Agregar un símbolo a la lista
          </label>
          <input
            id="watchlist-add"
            data-testid="watchlist-add-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value.toUpperCase())}
            placeholder="Agregar símbolo, ej. PYPL"
            autoComplete="off"
            spellCheck={false}
            maxLength={8}
            className="h-8 min-w-0 flex-1 rounded-[3px] border border-line-strong bg-ink px-2.5 text-[13px] font-semibold tracking-[0.02em] text-fg placeholder:font-normal placeholder:tracking-normal placeholder:text-dim focus:border-accent focus:outline-none"
          />
          <button
            type="submit"
            data-testid="watchlist-add-button"
            disabled={busy || !draft.trim()}
            className="h-8 rounded-[3px] bg-submit px-3.5 text-[12.5px] font-semibold text-white transition-colors hover:bg-submit-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? "AGREGANDO…" : "AGREGAR"}
          </button>
        </div>
        {error && (
          <p data-testid="watchlist-error" role="alert" className="mt-2 text-[12px] text-loss">
            {error}
          </p>
        )}
      </form>
    </Panel>
  );
}

const EMPTY_POINTS: PricePoint[] = [];

interface WatchlistRowProps {
  ticker: string;
  quote: PriceUpdate | null | undefined;
  points: PricePoint[];
  selected: boolean;
  held?: boolean;
  changeHint: string;
  onSelect: (ticker: string) => void;
  onRemove: (ticker: string) => void;
}

export function WatchlistRow({ ticker, quote, points, selected, held = false, changeHint, onSelect, onRemove }: WatchlistRowProps) {
  const flash = useFlash(quote?.price);
  const sign = quote ? pnlSign(quote.change_percent) : "zero";

  return (
    <li
      data-testid={`watchlist-row-${ticker}`}
      data-direction={quote?.direction ?? "flat"}
      data-selected={selected}
      className={`group relative flex items-center border-b border-line/60 ${
        selected ? "bg-raised" : "hover:bg-raised/60"
      }`}
    >
      {selected && <span className="absolute inset-y-0 left-0 w-[2px] bg-accent" aria-hidden="true" />}
      <button
        type="button"
        onClick={() => onSelect(ticker)}
        aria-pressed={selected}
        aria-label={`Seleccionar ${ticker}`}
        className={`${COLUMNS} h-11 min-w-0 flex-1 pl-2 text-left focus-visible:outline-offset-[-2px]`}
      >
        <span className="min-w-0"><span className={`font-wide block truncate text-[12.5px] font-bold tracking-[0.01em] ${selected ? "text-accent" : "text-fg"}`}>{ticker}{held && <span className="ml-1 text-[9px] text-gain" title="Posición abierta">●</span>}</span><span className="block truncate text-[8px] text-dim">{STOCK_NAMES[ticker] ?? "Acción"}</span></span>
        <span className="flex justify-end">
          <Sparkline ticker={ticker} points={points} width={30} height={18} />
        </span>
        <span
          data-testid={`watchlist-price-${ticker}`}
          className={`price-cell tabular rounded-[2px] py-0.5 text-right text-[11px] font-medium text-fg ${flash}`}
        >
          {quote ? formatPrice(quote.price) : "—"}
        </span>
        <span
          data-testid={`watchlist-change-${ticker}`}
          title={changeHint}
          className={`tabular text-right text-[10px] font-medium ${SIGN_TEXT[sign]}`}
        >
          {quote ? formatPercent(quote.change_percent) : "—"}
        </span>
      </button>
      <button
        type="button"
        data-testid={`watchlist-remove-${ticker}`}
        onClick={() => onRemove(ticker)}
        aria-label={`Quitar ${ticker} de la lista`}
        title={`Quitar ${ticker}`}
        className="mr-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-[3px] text-dim opacity-0 transition-opacity group-hover:opacity-100 hover:bg-line hover:text-fg focus-visible:opacity-100"
      >
        <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
          <path d="M1.5 1.5l7 7M8.5 1.5l-7 7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </svg>
      </button>
    </li>
  );
}
