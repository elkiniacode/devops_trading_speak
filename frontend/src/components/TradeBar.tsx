"use client";

import { type FormEvent, useEffect, useState } from "react";

import { formatMoney, formatQuantity } from "@/lib/format";
import type { Selection } from "@/state/appData";
import type { PriceMap, Trade, TradeSide } from "@/lib/types";

export type TradeOutcome = { ok: true; trade: Trade } | { ok: false; error: string };

interface TradeBarProps {
  selection: Selection | null;
  prices: PriceMap;
  /** Shares held per ticker, for the "Holding" hint. */
  holdings: Record<string, number>;
  onTrade: (ticker: string, quantity: number, side: TradeSide) => Promise<TradeOutcome>;
}

interface Message {
  status: "success" | "error";
  text: string;
}

export function describeTrade(trade: Trade): string {
  const verb = trade.side === "buy" ? "Bought" : "Sold";
  return `${verb} ${formatQuantity(trade.quantity)} ${trade.ticker} at ${formatMoney(trade.price)} (${formatMoney(trade.total)})`;
}

/** Market orders: instant fill at the current price, no confirmation (PLAN §2). */
export function TradeBar({ selection, prices, holdings, onTrade }: TradeBarProps) {
  const [ticker, setTicker] = useState("");
  const [quantity, setQuantity] = useState("");
  const [busy, setBusy] = useState<TradeSide | null>(null);
  const [message, setMessage] = useState<Message | null>(null);

  // A watchlist click pre-fills the ticker (CONTRACTS R31); the default selection doesn't.
  useEffect(() => {
    if (selection && selection.seq > 0) setTicker(selection.ticker);
  }, [selection]);

  const symbol = ticker.trim().toUpperCase();
  const qty = Number(quantity);
  const price = symbol ? prices[symbol]?.price : undefined;
  const estimate = price !== undefined && qty > 0 ? qty * price : null;
  const held = symbol ? holdings[symbol] : undefined;

  async function execute(side: TradeSide) {
    if (busy) return;
    if (!symbol) {
      setMessage({ status: "error", text: "Enter a ticker symbol." });
      return;
    }
    if (!quantity.trim() || !Number.isFinite(qty) || qty <= 0) {
      setMessage({ status: "error", text: "Enter a quantity greater than 0." });
      return;
    }
    setBusy(side);
    setMessage(null);
    const outcome = await onTrade(symbol, qty, side);
    setBusy(null);
    if (outcome.ok) {
      setMessage({ status: "success", text: describeTrade(outcome.trade) });
    } else {
      setMessage({ status: "error", text: outcome.error });
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
  }

  return (
    <section aria-label="Trade" className="shrink-0 rounded-[3px] border border-line bg-panel px-3 py-2.5">
      <form onSubmit={onSubmit} className="flex flex-wrap items-center gap-2">
        <h2 className="mr-1 text-[12.5px] font-semibold text-fg">Trade</h2>
        <label className="sr-only" htmlFor="trade-ticker">
          Ticker
        </label>
        <input
          id="trade-ticker"
          data-testid="trade-ticker-input"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          placeholder="Symbol"
          autoComplete="off"
          spellCheck={false}
          maxLength={8}
          className="font-wide h-8 w-[104px] rounded-[3px] border border-line-strong bg-ink px-2.5 text-[13px] font-bold tracking-[0.02em] text-accent placeholder:font-normal placeholder:tracking-normal placeholder:text-dim focus:border-accent focus:outline-none"
        />
        <label className="sr-only" htmlFor="trade-quantity">
          Quantity
        </label>
        <input
          id="trade-quantity"
          data-testid="trade-quantity-input"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          placeholder="Shares"
          inputMode="decimal"
          type="number"
          min="0"
          step="any"
          className="tabular h-8 w-[104px] rounded-[3px] border border-line-strong bg-ink px-2.5 text-[13px] text-fg placeholder:text-dim focus:border-accent focus:outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
        />
        <button
          type="button"
          data-testid="trade-buy-button"
          disabled={busy !== null}
          onClick={() => execute("buy")}
          className="h-8 min-w-[64px] rounded-[3px] bg-submit px-4 text-[12.5px] font-semibold text-white transition-colors hover:bg-submit-hover disabled:cursor-wait disabled:opacity-60"
        >
          {busy === "buy" ? "Buying…" : "Buy"}
        </button>
        <button
          type="button"
          data-testid="trade-sell-button"
          disabled={busy !== null}
          onClick={() => execute("sell")}
          className="h-8 min-w-[64px] rounded-[3px] border border-submit px-4 text-[12.5px] font-semibold text-fg transition-colors hover:bg-submit/25 disabled:cursor-wait disabled:opacity-60"
        >
          {busy === "sell" ? "Selling…" : "Sell"}
        </button>
        <div className="tabular ml-1 flex gap-3 text-[12px] text-muted">
          {estimate !== null && <span>Est. {formatMoney(estimate)}</span>}
          {held !== undefined && <span>Holding {formatQuantity(held)}</span>}
        </div>
      </form>
      <p
        data-testid={message ? "trade-message" : undefined}
        data-status={message?.status}
        role={message?.status === "error" ? "alert" : "status"}
        className={`mt-1.5 min-h-[18px] text-[12px] ${message?.status === "error" ? "text-loss" : "text-gain"}`}
      >
        {message?.text ?? <span className="text-dim">Market orders fill instantly at the last price.</span>}
      </p>
    </section>
  );
}
