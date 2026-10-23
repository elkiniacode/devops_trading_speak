"use client";

import { useState } from "react";

import { formatMoney, formatPercent, formatPrice, formatQuantity, formatSignedMoney, pnlSign } from "@/lib/format";
import type { LivePosition } from "@/lib/portfolio";

import { Panel } from "./Panel";
import { SIGN_TEXT } from "./tone";

interface PositionsTableProps {
  positions: LivePosition[] | null;
  onSelect: (ticker: string) => void;
  risk?: Record<string, { stop_loss: number | null; take_profit: number | null }>;
  onClose?: (ticker: string) => Promise<string | null>;
  onRisk?: (ticker: string, stopLoss: number | null, takeProfit: number | null) => Promise<string | null>;
}

const PRICE_NOTE = {
  live: undefined,
  rest: "Último precio conocido; aún no hay precio en vivo",
  cost: "Sin precio disponible: valorado al costo",
} as const;

export function PositionsTable({ positions, onSelect, risk, onClose, onRisk }: PositionsTableProps) {
  const [editing, setEditing] = useState<string | null>(null);
  const [stopLoss, setStopLoss] = useState("");
  const [takeProfit, setTakeProfit] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function saveRisk(ticker: string) {
    if (!onRisk) return;
    setBusy(true); setError("");
    const failure = await onRisk(ticker, stopLoss ? Number(stopLoss) : null, takeProfit ? Number(takeProfit) : null);
    setBusy(false);
    if (failure) setError(failure); else setEditing(null);
  }
  async function close(ticker: string) {
    if (!onClose) return;
    setBusy(true); setError("");
    const failure = await onClose(ticker);
    setBusy(false);
    if (failure) setError(failure);
  }
  return (
    <Panel
      title="Posiciones"
      meta={positions && positions.length > 0 ? `${positions.length} abiertas` : undefined}
      className="min-h-[150px] flex-1"
      bodyClassName="overflow-auto"
    >
      <table data-testid="positions-table" className="w-full border-collapse text-[12.5px]">
        <thead className="sticky top-0 z-10 bg-panel text-[11px] text-dim">
          <tr className="border-b border-line">
            <th scope="col" className="py-1.5 pl-3 text-left font-normal">
              Símbolo
            </th>
            <th scope="col" className="px-2 text-right font-normal">
              Cant.
            </th>
            <th scope="col" className="px-2 text-right font-normal">
              Costo prom.
            </th>
            <th scope="col" className="px-2 text-right font-normal">
              Precio
            </th>
            <th scope="col" className="px-2 text-right font-normal">
              Valor
            </th>
            <th scope="col" className="px-2 text-right font-normal">
              P&amp;L abierto
            </th>
            <th scope="col" className="pr-3 pl-2 text-right font-normal">
              P&amp;L %
            </th>
            {onClose && <th scope="col" className="px-2 text-right font-normal">Acciones</th>}
          </tr>
        </thead>
        <tbody className="tabular">
          {positions?.map((p) => {
            const sign = pnlSign(p.unrealized_pnl);
            return (
              <tr
                key={p.ticker}
                data-testid={`position-row-${p.ticker}`}
                onClick={() => onSelect(p.ticker)}
                className="cursor-pointer border-b border-line/60 hover:bg-raised/60"
              >
                <th scope="row" className="py-1.5 pl-3 text-left">
                  <span className="font-wide text-[12.5px] font-bold text-fg">{p.ticker}</span>
                </th>
                <td data-testid={`position-qty-${p.ticker}`} className="px-2 text-right text-fg">
                  {formatQuantity(p.quantity)}
                </td>
                <td data-testid={`position-avg-cost-${p.ticker}`} className="px-2 text-right text-muted">
                  {formatMoney(p.avg_cost)}
                </td>
                <td
                  data-testid={`position-price-${p.ticker}`}
                  title={PRICE_NOTE[p.priceSource]}
                  className={`px-2 text-right ${p.priceSource === "live" ? "text-fg" : "text-accent"}`}
                >
                  {p.priceSource === "cost" ? "—" : formatPrice(p.price)}
                </td>
                <td className="px-2 text-right text-fg">{formatMoney(p.market_value)}</td>
                <td data-testid={`position-pnl-${p.ticker}`} className={`px-2 text-right font-medium ${SIGN_TEXT[sign]}`}>
                  {formatSignedMoney(p.unrealized_pnl)}
                </td>
                <td
                  data-testid={`position-pnl-percent-${p.ticker}`}
                  className={`pr-3 pl-2 text-right font-medium ${SIGN_TEXT[sign]}`}
                >
                  {formatPercent(p.unrealized_pnl_percent)}
                </td>
                {onClose && <td className="whitespace-nowrap px-2 text-right"><button disabled={busy} onClick={(event) => { event.stopPropagation(); setEditing(p.ticker); setStopLoss(String(risk?.[p.ticker]?.stop_loss ?? "")); setTakeProfit(String(risk?.[p.ticker]?.take_profit ?? "")); }} className="mr-2 text-accent">RIESGO</button><button disabled={busy} onClick={(event) => { event.stopPropagation(); void close(p.ticker); }} className="text-loss">CERRAR</button></td>}
              </tr>
            );
          })}
        </tbody>
      </table>
      {editing && <div className="flex flex-wrap items-center gap-2 border-t border-line p-2 text-[10px]"><span className="text-accent">RIESGO · {editing}</span><label>SL <input aria-label="Stop loss de posición" type="number" min="0" step="any" value={stopLoss} onChange={(event) => setStopLoss(event.target.value)} className="w-20 rounded border border-line bg-ink px-1.5 py-1 text-fg" /></label><label>TP <input aria-label="Take profit de posición" type="number" min="0" step="any" value={takeProfit} onChange={(event) => setTakeProfit(event.target.value)} className="w-20 rounded border border-line bg-ink px-1.5 py-1 text-fg" /></label><button disabled={busy} onClick={() => void saveRisk(editing)} className="text-gain">GUARDAR</button><button onClick={() => setEditing(null)} className="text-muted">SALIR</button><span className="text-muted">Deja ambos vacíos para quitar los niveles.</span></div>}
      {error && <p role="alert" className="px-3 text-[10px] text-loss">{error}</p>}
      {positions?.length === 0 && (
        <p className="px-3 py-4 text-[12.5px] text-muted">
          Aún no tienes posiciones. Usa el panel de órdenes para comprar acciones.
        </p>
      )}
      {positions === null && <p className="px-3 py-4 text-[12.5px] text-dim">Cargando posiciones…</p>}
    </Panel>
  );
}
