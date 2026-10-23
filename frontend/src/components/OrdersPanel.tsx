"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { formatMoney } from "@/lib/format";
import type { PendingOrder } from "@/lib/types";

export function OrdersPanel({ orders, onChanged }: { orders: PendingOrder[]; onChanged: () => void }) {
  const [editing, setEditing] = useState<string | null>(null);
  const [trigger, setTrigger] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function update(id: string) {
    setBusy(true); setError("");
    try {
      await api.editOrder(id, { trigger_price: Number(trigger) });
      setEditing(null); onChanged();
    } catch (reason) { setError(reason instanceof ApiError ? reason.detail : "No se pudo editar la orden."); }
    finally { setBusy(false); }
  }
  async function cancel(id: string) {
    setBusy(true); setError("");
    try { await api.cancelOrder(id); onChanged(); }
    catch (reason) { setError(reason instanceof ApiError ? reason.detail : "No se pudo cancelar la orden."); }
    finally { setBusy(false); }
  }
  return <div className="max-h-[220px] overflow-auto text-[10px]">
    {error && <p role="alert" className="pb-2 text-loss">{error}</p>}
    {orders.length ? orders.map((order) => <div key={order.id} className="border-b border-line py-2">
      <div className="flex items-center gap-3"><span className={order.status === "filled" ? "text-gain" : order.status === "rejected" ? "text-loss" : "text-accent"}>{order.status.toUpperCase()}</span><span>{order.side === "buy" ? "COMPRA" : "VENTA"} {order.ticker}</span><span>{order.type.toUpperCase()} · {formatMoney(order.trigger_price)}</span>
        {order.status === "pending" && <div className="ml-auto flex gap-2"><button disabled={busy} onClick={() => { setEditing(order.id); setTrigger(String(order.trigger_price)); }} className="text-accent">EDITAR</button><button disabled={busy} onClick={() => void cancel(order.id)} className="text-loss">CANCELAR</button></div>}
      </div>
      {order.reason && <p className="mt-1 text-loss">{order.reason}</p>}
      {editing === order.id && <div className="mt-2 flex items-center gap-2"><label>ACTIVACIÓN <input aria-label={`Precio de activación de ${order.ticker}`} type="number" min="0" step="any" value={trigger} onChange={(event) => setTrigger(event.target.value)} className="ml-1 w-24 rounded border border-line bg-ink px-2 py-1 text-fg" /></label><button disabled={busy || !trigger} onClick={() => void update(order.id)} className="text-accent">GUARDAR</button><button onClick={() => setEditing(null)} className="text-muted">SALIR</button></div>}
    </div>) : <p className="py-8 text-center text-muted">Sin órdenes pendientes o recientes.</p>}
  </div>;
}
