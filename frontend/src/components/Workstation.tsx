"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, API_BASE, ApiError } from "@/lib/api";
import { valuePortfolio } from "@/lib/portfolio";
import type { PricePoint } from "@/lib/priceStore";
import type { PendingOrder, TradeSide } from "@/lib/types";
import { formatMoney } from "@/lib/format";
import { AppDataProvider, useAppData } from "@/state/appData";
import { PriceProvider, usePrices } from "@/state/prices";

import { ChatPanel } from "./ChatPanel";
import { Header } from "./Header";
import { Heatmap } from "./Heatmap";
import { MainChart } from "./MainChart";
import { OrdersPanel } from "./OrdersPanel";
import { PnlChart } from "./PnlChart";
import { PositionsTable } from "./PositionsTable";
import { SentimentCard } from "./SentimentCard";
import { Watchlist } from "./Watchlist";

const NO_POINTS: PricePoint[] = [];

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.detail : "Ocurrió un error. Inténtalo de nuevo.";
}

const loadChatHistory = () => api.chatHistory().then((r) => r.messages);

export function Workstation() {
  return (
    <PriceProvider>
      <AppDataProvider>
        <WorkstationLayout />
      </AppDataProvider>
    </PriceProvider>
  );
}

export function WorkstationLayout() {
  const { prices, history, status } = usePrices();
  const { portfolio, watchlist, snapshots, health, loadError, selection, selectTicker, refreshAll, setWatchlist } =
    useAppData();
  const [chatOpen, setChatOpen] = useState(true);
  const [desktopReady, setDesktopReady] = useState(false);
  const [extras, setExtras] = useState<{ orders: PendingOrder[]; activity: Array<{ id: string; message: string; created_at: string }>; trades: Array<{ id: string; ticker: string; side: string; quantity: number; price: number; executed_at: string }>; risk: Array<{ ticker: string; stop_loss: number | null; take_profit: number | null }> }>({ orders: [], activity: [], trades: [], risk: [] });
  const [dock, setDock] = useState<"positions" | "markets" | "orders" | "history" | "journal">("positions");
  const reloadExtras = useCallback(() => {
    void api.workstation().then((raw) => setExtras({
      orders: Array.isArray(raw.orders) ? raw.orders as typeof extras.orders : [],
      activity: Array.isArray(raw.activity) ? raw.activity as typeof extras.activity : [],
      trades: Array.isArray(raw.trades) ? raw.trades as typeof extras.trades : [],
      risk: Array.isArray(raw.risk) ? raw.risk as typeof extras.risk : [],
    })).catch(() => undefined);
  }, []);
  useEffect(() => { reloadExtras(); }, [reloadExtras]);

  useEffect(() => {
    if (!window.matchMedia) { setDesktopReady(window.innerWidth >= 1200); return; }
    const media = window.matchMedia("(min-width: 1200px)");
    const update = () => setDesktopReady(media.matches);
    update(); media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, []);

  // After the stream drops and comes back, or once the server is reachable after a failed
  // first load, refetch everything: trades may have happened while we were away.
  const wasConnected = useRef(false);
  const loadErrorRef = useRef(loadError);
  useEffect(() => {
    loadErrorRef.current = loadError;
  }, [loadError]);
  useEffect(() => {
    if (status !== "connected") return;
    if (wasConnected.current || loadErrorRef.current) { void refreshAll(); reloadExtras(); }
    wasConnected.current = true;
  }, [status, refreshAll, reloadExtras]);

  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const source = new EventSource(`${API_BASE}/api/stream/workstation?account_only=1`);
    if (typeof source.addEventListener !== "function") { source.close(); return; }
    let version: number | null = null;
    const onAccount = (event: MessageEvent) => {
      try {
        const incoming = (JSON.parse(event.data) as { version: number }).version;
        if (version !== null && incoming !== version) { void refreshAll(); reloadExtras(); }
        version = incoming;
      } catch { /* malformed event: next account event replaces it */ }
    };
    source.addEventListener("account", onAccount);
    return () => { source.removeEventListener("account", onAccount); source.close(); };
  }, [refreshAll, reloadExtras]);

  const valuation = useMemo(() => (portfolio ? valuePortfolio(portfolio, prices) : null), [portfolio, prices]);

  const holdings = useMemo(
    () => Object.fromEntries((portfolio?.positions ?? []).map((p) => [p.ticker, p.quantity])),
    [portfolio],
  );

  const onClosePosition = useCallback(async (ticker: string) => {
    try { await api.closePosition(ticker); await refreshAll(); reloadExtras(); return null; }
    catch (reason) { return errorText(reason); }
  }, [refreshAll, reloadExtras]);
  const onSetRisk = useCallback(async (ticker: string, stopLoss: number | null, takeProfit: number | null) => {
    try { await api.setRisk(ticker, { stop_loss: stopLoss, take_profit: takeProfit }); reloadExtras(); return null; }
    catch (reason) { return errorText(reason); }
  }, [reloadExtras]);

  const onAdd = useCallback(
    async (ticker: string) => {
      try {
        setWatchlist((await api.addToWatchlist(ticker)).watchlist);
        void refreshAll();
        return null;
      } catch (err) {
        return errorText(err);
      }
    },
    [setWatchlist, refreshAll],
  );

  const onRemove = useCallback(
    async (ticker: string) => {
      try {
        setWatchlist((await api.removeFromWatchlist(ticker)).watchlist);
        void refreshAll();
        return null;
      } catch (err) {
        return errorText(err);
      }
    },
    [setWatchlist, refreshAll],
  );

  const onChatActions = useCallback(() => void refreshAll(), [refreshAll]);
  const toggleChat = useCallback(() => setChatOpen((open) => !open), []);
  const closeChat = useCallback(() => setChatOpen(false), []);

  const chartTicker = selection?.ticker ?? null;
  const mode = health?.market_data ?? null;
  const sendChat = useCallback((message: string) => api.chat(message, { ticker: chartTicker }), [chartTicker]);

  if (!desktopReady) return <main className="grid min-h-dvh place-items-center bg-ink p-8 text-center"><div className="max-w-md"><p className="mb-3 text-[10px] tracking-[0.22em] text-accent">IA REVOLUTIONS · FINALLY</p><h1 className="font-heading text-2xl font-bold">Terminal de escritorio</h1><p className="mt-3 text-sm leading-relaxed text-muted">Para usar el terminal de trading, abre esta página en una pantalla de al menos 1200 píxeles de ancho.</p></div></main>;

  return (
    <div className="flex min-h-dvh flex-col md:h-dvh md:overflow-hidden">
      <Header
        valuation={valuation}
        status={status}
        mode={mode}
        chatOpen={chatOpen}
        onToggleChat={toggleChat}
      />
      {loadError && (
        <div role="alert" className="shrink-0 border-b border-accent/30 bg-accent/10 px-4 py-1.5 text-[12.5px] text-accent">
          {loadError} El terminal volverá a intentarlo cuando se reconecten los precios.
        </div>
      )}

      <div className="relative flex min-h-0 flex-1">
        <main className="grid min-h-0 min-w-0 flex-1 gap-2 p-2 md:grid-cols-[250px_minmax(0,1fr)] xl:pr-0">
          <div className="min-h-0 max-md:h-[440px]">
            <Watchlist
              items={watchlist}
              prices={prices}
              history={history}
              selectedTicker={chartTicker}
              mode={mode}
              heldTickers={new Set(Object.keys(holdings))}
              onSelect={selectTicker}
              onAdd={onAdd}
              onRemove={onRemove}
            />
          </div>

          <div className="flex min-h-0 min-w-0 flex-col gap-2 md:overflow-y-auto md:pr-2">
            <MainChart
              ticker={chartTicker}
              quote={chartTicker ? prices[chartTicker] : null}
              points={(chartTicker && history[chartTicker]) || NO_POINTS}
              mode={mode}
              levels={{ entry: portfolio?.positions.find((position) => position.ticker === chartTicker)?.avg_cost,
                stopLoss: extras.risk.find((risk) => risk.ticker === chartTicker)?.stop_loss,
                takeProfit: extras.risk.find((risk) => risk.ticker === chartTicker)?.take_profit,
                pending: extras.orders.filter((order) => order.status === "pending" && order.ticker === chartTicker).map((order) => order.trigger_price) }}
            />
            <section className="min-h-[260px] flex-1 rounded border border-line bg-panel p-2">
              <nav className="mb-2 flex flex-wrap gap-1 border-b border-line pb-2" aria-label="Paneles del terminal">
                {([["positions", "POSICIONES"], ["markets", "MERCADOS"], ["orders", "ÓRDENES"], ["history", "HISTORIAL"], ["journal", "DIARIO"]] as const).map(([key, label]) => <button key={key} onClick={() => setDock(key)} aria-pressed={dock === key} className={`rounded px-2.5 py-1.5 text-[9px] font-bold tracking-wide ${dock === key ? "bg-accent/10 text-accent" : "text-muted hover:text-fg"}`}>{label}</button>)}
              </nav>
              <div hidden={dock !== "positions"} className="h-[190px]"><PositionsTable positions={valuation?.positions ?? null} onSelect={selectTicker} risk={Object.fromEntries(extras.risk.map((item) => [item.ticker, item]))} onClose={onClosePosition} onRisk={onSetRisk} /></div>
              <div hidden={dock !== "markets"} className="grid gap-1.5 lg:h-[220px] lg:grid-cols-2"><Heatmap positions={valuation?.positions ?? null} onSelect={selectTicker} /><PnlChart snapshots={snapshots} liveTotal={valuation?.totalValue ?? null} /></div>
              <div hidden={dock !== "orders"}><OrdersPanel orders={extras.orders} onChanged={() => { reloadExtras(); void refreshAll(); }} /></div>
              <div hidden={dock !== "history"} className="max-h-[220px] overflow-auto text-[10px]">{extras.trades.length ? extras.trades.map(trade => <div key={trade.id} className="flex gap-3 border-b border-line py-2"><time className="text-muted">{new Date(trade.executed_at).toLocaleString()}</time><span className={trade.side === "buy" ? "text-gain" : "text-loss"}>{trade.side.toUpperCase()} {trade.ticker}</span><span>{trade.quantity} × {formatMoney(trade.price)}</span></div>) : <p className="py-8 text-center text-muted">Aún no hay operaciones.</p>}</div>
              <div hidden={dock !== "journal"} className="max-h-[220px] overflow-auto text-[10px]">{extras.activity.length ? extras.activity.map(event => <div key={event.id} className="flex gap-3 border-b border-line py-2"><time className="shrink-0 text-muted">{new Date(event.created_at).toLocaleString()}</time><span>{event.message}</span></div>) : <p className="py-8 text-center text-muted">El diario aparecerá aquí cuando haya actividad.</p>}</div>
            </section>
          </div>
        </main>

        <div className="flex w-[320px] shrink-0 flex-col gap-2 overflow-y-auto p-2 pl-0">
          <OrderTicket ticker={chartTicker} quote={chartTicker ? prices[chartTicker] : undefined} holdings={holdings} onDone={() => { void refreshAll(); reloadExtras(); }} />
          <SentimentCard ticker={chartTicker} />
          {chatOpen ? <ChatPanel
            open={chatOpen}
            onClose={closeChat}
            send={sendChat}
            loadHistory={loadChatHistory}
            onActions={onChatActions}
          /> : <button onClick={() => setChatOpen(true)} className="rounded border border-line bg-panel p-3 text-left text-[11px] text-accent">ABRIR ASISTENTE IA</button>}
        </div>
      </div>
    </div>
  );
}

function OrderTicket({ ticker, quote, holdings, onDone }: { ticker: string | null; quote?: import("@/lib/types").PriceUpdate; holdings: Record<string, number>; onDone: () => void }) {
  const [side, setSide] = useState<TradeSide>("buy");
  const [kind, setKind] = useState<"market" | "limit" | "stop">("market");
  const [notional, setNotional] = useState("500");
  const [trigger, setTrigger] = useState("");
  const [stopLoss, setStopLoss] = useState("");
  const [takeProfit, setTakeProfit] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const clientId = useRef<string | null>(null);
  useEffect(() => { clientId.current = null; }, [ticker, side, kind, notional, trigger, stopLoss, takeProfit]);
  async function place() {
    if (!ticker || busy) return;
    if (!Number.isFinite(Number(notional)) || Number(notional) <= 0 || (kind !== "market" && (!trigger || Number(trigger) <= 0))) { setError("Ingresa un monto y un precio de activación válidos."); return; }
    setBusy(true); setError(""); setMessage("");
    try {
      clientId.current ??= crypto.randomUUID();
      const response = await api.order({ ticker, side, type: kind, notional: Number(notional), client_order_id: clientId.current, ...(kind === "market" ? {} : { trigger_price: Number(trigger) }), ...(side === "buy" && stopLoss ? { stop_loss: Number(stopLoss) } : {}), ...(side === "buy" && takeProfit ? { take_profit: Number(takeProfit) } : {}) });
      clientId.current = null;
      setMessage(response.status === "filled" ? "ORDEN EJECUTADA" : "ORDEN PENDIENTE"); onDone();
    } catch (err) { setError(errorText(err)); }
    finally { setBusy(false); }
  }
  const sellable = ticker ? (holdings[ticker] ?? 0) * (quote?.price ?? 0) : 0;
  const estimated = quote?.price && Number(notional) > 0 ? Number(notional) / (kind === "market" ? quote.price : Number(trigger) || quote.price) : 0;
  return <section className="shrink-0 rounded border border-line bg-panel p-3" aria-label="Orden">
    <header className="mb-2 flex items-center justify-between"><h2 className="font-heading text-[12px] font-bold tracking-wide text-accent">01 · ORDEN · {ticker ?? "—"}</h2><span className="tabular text-[11px]">{quote ? formatMoney(quote.price) : "—"}</span></header>
    <div className="mb-2 grid grid-cols-2 gap-1"><button onClick={() => setSide("buy")} className={`h-9 rounded border text-[11px] font-bold ${side === "buy" ? "border-gain bg-gain/10 text-gain" : "border-line text-muted"}`}>COMPRAR</button><button onClick={() => setSide("sell")} className={`h-9 rounded border text-[11px] font-bold ${side === "sell" ? "border-loss bg-loss/10 text-loss" : "border-line text-muted"}`}>VENDER</button></div>
    <div className="mb-2 flex gap-1">{(["market", "limit", "stop"] as const).map((value) => <button key={value} onClick={() => setKind(value)} className={`flex-1 rounded border py-1.5 text-[9px] ${kind === value ? "border-accent text-accent" : "border-line text-muted"}`}>{value === "market" ? "MERCADO" : value === "limit" ? "LÍMITE" : "STOP"}</button>)}</div>
    {kind !== "market" && <label className="mb-2 block text-[9px] text-muted">PRECIO DE ACTIVACIÓN<input value={trigger} onChange={(event) => setTrigger(event.target.value)} type="number" min="0" step="any" className="mt-1 block h-8 w-full rounded border border-line-strong bg-ink px-2 text-[11px] text-fg" placeholder={quote ? String(quote.price) : "0.00"} /></label>}
    <label className="block text-[9px] text-muted">MONTO (USD)<input value={notional} onChange={(event) => setNotional(event.target.value)} type="number" min="1" step="any" className="mt-1 block h-8 w-full rounded border border-line-strong bg-ink px-2 text-[11px] text-fg" /></label>
    {side === "buy" && <div className="mt-2 grid grid-cols-2 gap-2"><label className="text-[9px] text-muted">STOP LOSS<input aria-label="Stop loss" value={stopLoss} onChange={event => setStopLoss(event.target.value)} type="number" min="0" step="any" placeholder="Opcional" className="mt-1 block h-8 w-full rounded border border-line-strong bg-ink px-2 text-[10px] text-fg" /></label><label className="text-[9px] text-muted">TAKE PROFIT<input aria-label="Take profit" value={takeProfit} onChange={event => setTakeProfit(event.target.value)} type="number" min="0" step="any" placeholder="Opcional" className="mt-1 block h-8 w-full rounded border border-line-strong bg-ink px-2 text-[10px] text-fg" /></label></div>}
    <div className="mt-1 flex gap-1">{[100, 500, 1000].map((value) => <button key={value} onClick={() => setNotional(String(value))} className="rounded border border-line px-2 py-1 text-[9px] text-muted">${value}</button>)}<span className="ml-auto text-[9px] text-muted">{side === "sell" ? `DISP. ${formatMoney(sellable)}` : "CUENTA SIMULADA"}</span></div>
    <p className="mt-2 text-[9px] text-muted">ESTIMADO: {Number.isFinite(estimated) ? estimated.toFixed(4) : "0.0000"} acciones · Sin comisiones</p>
    {error && <p role="alert" className="mt-2 text-[10px] text-loss">{error}</p>}{message && <p role="status" className="mt-2 text-[10px] text-gain">{message}</p>}
    <button disabled={!ticker || busy} onClick={() => void place()} className={`mt-2 h-9 w-full rounded border text-[10px] font-bold ${side === "buy" ? "border-gain bg-gain/10 text-gain" : "border-loss bg-loss/10 text-loss"}`}>{busy ? "ENVIANDO…" : `${side === "buy" ? "COMPRAR" : "VENDER"} ${ticker ?? ""}`}</button>
  </section>;
}

