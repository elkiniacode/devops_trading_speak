"use client";

import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api";
import { formatMoney, formatQuantity } from "@/lib/format";
import type { ChatActions, ChatMessage, TradeAction, WatchlistAction } from "@/lib/types";

export const MAX_MESSAGE_LENGTH = 2000;

const SUGGESTIONS = ["How is my portfolio doing?", "Buy 5 NVDA", "Add PYPL to my watchlist"];

interface ChatPanelProps {
  open: boolean;
  onClose: () => void;
  send: (message: string) => Promise<ChatMessage>;
  loadHistory: () => Promise<ChatMessage[]>;
  /** Called after a reply that carried trades or watchlist changes, so the app can refetch. */
  onActions: () => void;
}

export function hasActions(actions: ChatActions | null): boolean {
  return !!actions && (actions.trades.length > 0 || actions.watchlist_changes.length > 0 || (actions.orders?.length ?? 0) > 0 || (actions.closes?.length ?? 0) > 0 || (actions.risks?.length ?? 0) > 0);
}

export function describeTradeAction(a: TradeAction): string {
  const qty = `${formatQuantity(a.quantity)} ${a.ticker}`;
  if (a.status === "ok") {
    const verb = a.side === "buy" ? "Bought" : "Sold";
    return a.price != null ? `${verb} ${qty} at ${formatMoney(a.price)}` : `${verb} ${qty}`;
  }
  const verb = a.side === "buy" ? "Buy" : "Sell";
  return `${verb} ${qty} failed: ${a.error ?? "rejected"}`;
}

export function describeWatchlistAction(a: WatchlistAction): string {
  if (a.status === "ok") {
    return a.action === "add" ? `${a.ticker} added to watchlist` : `${a.ticker} removed from watchlist`;
  }
  const verb = a.action === "add" ? "Add" : "Remove";
  return `${verb} ${a.ticker} failed: ${a.error ?? "rejected"}`;
}

export function ChatPanel({ open, onClose, send, loadHistory, onActions }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Restore the conversation after a reload (CONTRACTS R24).
  useEffect(() => {
    let cancelled = false;
    loadHistory()
      .then((history) => {
        if (!cancelled) setMessages((local) => [...history, ...local.filter((m) => !history.some((h) => h.id === m.id))]);
      })
      .catch(() => {
        // An empty panel is fine; sending still works.
      });
    return () => {
      cancelled = true;
    };
  }, [loadHistory]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, loading, error]);

  async function submit(event?: FormEvent) {
    event?.preventDefault();
    const text = draft.trim();
    if (!text || loading) return;
    if (text.length > MAX_MESSAGE_LENGTH) {
      setError(`El mensaje admite hasta ${MAX_MESSAGE_LENGTH.toLocaleString("es-CO")} caracteres.`);
      return;
    }
    const local: ChatMessage = {
      id: `local-${Date.now()}`,
      role: "user",
      content: text,
      actions: null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, local]);
    setDraft("");
    setError(null);
    setLoading(true);
    try {
      const reply = await send(text);
      setMessages((prev) => [...prev, reply]);
      if (hasActions(reply.actions)) onActions();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "The assistant did not respond. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submit();
    }
  }

  return (
    <aside
      id="chat-panel"
      data-testid="chat-panel"
      data-open={open}
      aria-label="Assistant"
      hidden={!open}
      className="flex min-h-[220px] min-h-0 w-full flex-1 flex-col border border-line bg-panel"
    >
      <header className="flex h-10 shrink-0 items-center gap-2 border-b border-line px-3">
        <span className="h-2.5 w-2.5 rounded-[2px] bg-accent" aria-hidden="true" />
        <h2 className="text-[13px] font-semibold text-fg">Assistant</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Contraer asistente"
          title="Contraer"
          className="ml-auto flex h-7 w-7 items-center justify-center rounded-[3px] text-muted hover:bg-raised hover:text-fg"
        >
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
            <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" />
          </svg>
        </button>
      </header>

      <div ref={scrollRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto px-3 py-3" aria-live="polite">
        {messages.length === 0 && !loading && (
          <div className="space-y-3 pt-2">
            <p className="text-[13px] leading-relaxed text-muted">
              Ask about your positions, risk, or P&amp;L. Tell me to buy, sell, or update your watchlist.
            </p>
            <div className="flex flex-wrap gap-1.5">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => {
                    setDraft(s);
                    inputRef.current?.focus();
                  }}
                  className="rounded-[3px] border border-line-strong px-2 py-1 text-[12px] text-fg hover:border-primary hover:text-primary"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => (
          <MessageView key={m.id} message={m} />
        ))}

        {loading && (
          <div data-testid="chat-loading" role="status" className="flex items-center gap-2 text-[12.5px] text-muted">
            <span className="flex gap-1" aria-hidden="true">
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-primary" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-primary" />
              <span className="typing-dot h-1.5 w-1.5 rounded-full bg-primary" />
            </span>
            FinAlly is thinking
          </div>
        )}

        {error && (
          <p
            data-testid="chat-error"
            role="alert"
            className="rounded-[3px] border border-loss/40 bg-loss/10 px-2.5 py-2 text-[12.5px] text-loss"
          >
            {error}
          </p>
        )}
      </div>

      <form onSubmit={submit} className="shrink-0 border-t border-line p-2.5">
        <label htmlFor="chat-input" className="sr-only">
          Message for the assistant
        </label>
        <textarea
          id="chat-input"
          ref={inputRef}
          data-testid="chat-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          maxLength={MAX_MESSAGE_LENGTH}
          placeholder="Ask FinAlly, e.g. buy 10 AAPL"
          className="block w-full resize-none rounded-[3px] border border-line-strong bg-ink px-2.5 py-2 text-[13px] leading-snug text-fg placeholder:text-dim focus:border-accent focus:outline-none"
        />
        <div className="mt-2 flex items-center justify-between">
          <span className="text-[9px] text-dim">Enter to send · Shift+Enter for a new line</span>
          <button
            type="submit"
            data-testid="chat-send-button"
            disabled={loading || !draft.trim()}
            className="h-8 rounded-[3px] bg-submit px-4 text-[12.5px] font-semibold text-white transition-colors hover:bg-submit-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            SEND
          </button>
        </div>
      </form>
    </aside>
  );
}

function MessageView({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div data-testid="chat-message" data-role="user" className="flex justify-end">
        <p className="max-w-[85%] rounded-[3px] bg-raised px-2.5 py-1.5 text-[13px] leading-snug whitespace-pre-wrap text-fg">
          {message.content}
        </p>
      </div>
    );
  }
  const actions = message.actions;
  return (
    <div data-testid="chat-message" data-role="assistant" className="border-l-2 border-primary/60 pl-2.5">
      <p className="text-[13px] leading-relaxed whitespace-pre-wrap text-fg">{message.content}</p>
      {actions && hasActions(actions) && (
        <ul className="mt-2 space-y-1">
          {actions.watchlist_changes.map((a, i) => (
            <ActionLine key={`w${i}`} kind="watchlist" ok={a.status === "ok"} text={describeWatchlistAction(a)} />
          ))}
          {actions.trades.map((a, i) => (
            <ActionLine key={`t${i}`} kind="trade" ok={a.status === "ok"} text={describeTradeAction(a)} />
          ))}
          {actions.orders?.map((a, i) => <ActionLine key={`o${i}`} kind="trade" ok={a.status === "ok"} text={a.status === "ok" ? `Orden ${a.type} ${a.side} ${a.ticker}: ${a.order_status}` : `Orden ${a.ticker}: ${a.error}`} />)}
          {actions.closes?.map((a, i) => <ActionLine key={`c${i}`} kind="trade" ok={a.status === "ok"} text={a.status === "ok" ? `${a.ticker} position closed` : `Close ${a.ticker}: ${a.error}`} />)}
          {actions.risks?.map((a, i) => <ActionLine key={`r${i}`} kind="trade" ok={a.status === "ok"} text={a.status === "ok" ? `Riesgo ${a.ticker} actualizado` : `Riesgo ${a.ticker}: ${a.error}`} />)}
        </ul>
      )}
    </div>
  );
}

function ActionLine({ kind, ok, text }: { kind: "trade" | "watchlist"; ok: boolean; text: string }) {
  return (
    <li
      data-testid="chat-action"
      data-kind={kind}
      data-status={ok ? "ok" : "failed"}
      className={`flex items-start gap-1.5 rounded-[2px] px-1.5 py-1 text-[12.5px] leading-snug ${
        ok ? "bg-gain/10 text-gain" : "bg-loss/10 text-loss"
      }`}
    >
      <span aria-hidden="true" className="font-bold">
        {ok ? "✓" : "✗"}
      </span>
      <span className="tabular">{text}</span>
    </li>
  );
}
