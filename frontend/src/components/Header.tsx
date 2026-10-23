import { formatMoney, formatPercent, formatSignedMoney, pnlSign } from "@/lib/format";
import type { LiveValuation } from "@/lib/portfolio";
import type { ConnectionStatus as Status } from "@/lib/priceStore";
import type { MarketMode } from "@/lib/types";

import { ConnectionStatus } from "./ConnectionStatus";
import { SIGN_TEXT } from "./tone";

const MODE_BADGE: Record<MarketMode, { label: string; hint: string }> = {
  simulator: { label: "SIM", hint: "Precios simulados" },
  "massive-snapshot": { label: "RETRASADO", hint: "Precios de mercado con el retraso de tu plan" },
  "massive-eod": { label: "CIERRE", hint: "Precios de cierre diario" },
};

interface HeaderProps {
  valuation: LiveValuation | null;
  status: Status;
  mode: MarketMode | null;
  chatOpen: boolean;
  onToggleChat: () => void;
}

export function Header({ valuation, status, mode, chatOpen, onToggleChat }: HeaderProps) {
  const badge = mode ? MODE_BADGE[mode] : null;
  const sign = valuation ? pnlSign(valuation.totalPnl) : "zero";
  const openPnl = valuation?.positions.reduce((sum, position) => sum + position.unrealized_pnl, 0) ?? 0;

  return (
    <header className="flex shrink-0 flex-wrap items-center gap-x-5 gap-y-2 border-b border-line bg-panel px-4 py-2.5 md:h-[52px] md:flex-nowrap md:py-0">
      <div className="order-1 flex items-center gap-2.5">
        <span className="h-3.5 w-3.5 rounded-[2px] bg-accent" aria-hidden="true" />
        <span className="font-wide text-[17px] font-bold tracking-[-0.01em] text-fg">IA REVOLUTIONS</span>
        <span className="rounded border border-accent/50 px-1 py-0.5 text-[8px] text-accent">CUENTA SIMULADA</span>
        {badge && (
          <span
            data-testid="market-mode"
            title={badge.hint}
            className="rounded-[3px] border border-line-strong px-1.5 py-[1px] text-[10.5px] font-semibold tracking-[0.04em] text-muted"
          >
            {badge.label}
          </span>
        )}
      </div>

      <div className="order-2 hidden h-6 w-px bg-line md:block" aria-hidden="true" />

      {/* On phones the figures drop to their own row below the brand and controls. */}
      <div className="order-4 flex basis-full flex-wrap items-baseline gap-x-5 gap-y-1 md:order-3 md:basis-auto md:flex-nowrap">
        <div className="flex min-w-0 items-baseline gap-3">
          <span className="hidden text-[9px] tracking-wider text-muted lg:inline">VALOR DEL PORTAFOLIO</span>
          <span
            data-testid="header-total-value"
            className="font-wide tabular text-[22px] font-semibold leading-none tracking-[-0.01em] text-fg"
              title={valuation && !valuation.complete ? "Algunas posiciones se valoran al costo porque no tienen precio disponible" : undefined}
          >
            {valuation ? formatMoney(valuation.totalValue) : "—"}
          </span>
          {valuation && (
            <span data-testid="header-pnl" className={`tabular text-[13px] font-medium ${SIGN_TEXT[sign]}`}>
              {formatSignedMoney(valuation.totalPnl)} ({formatPercent(valuation.totalPnlPercent)})
            </span>
          )}
        </div>

        <div className="flex items-baseline gap-2">
          <span className="text-[9px] tracking-wider text-muted">EFECTIVO</span>
          <span data-testid="header-cash" className="tabular text-[15px] font-semibold text-fg">
            {valuation ? formatMoney(valuation.cash) : "—"}
          </span>
        </div>
        <div className="flex items-baseline gap-2"><span className="text-[9px] tracking-wider text-muted">P/L ABIERTO</span><span className={`tabular text-[13px] ${SIGN_TEXT[pnlSign(openPnl)]}`}>{valuation ? formatSignedMoney(openPnl) : "—"}</span></div>
      </div>

      <div className="order-3 ml-auto flex items-center gap-4 md:order-4">
        <ConnectionStatus status={status} />
        <button
          type="button"
          data-testid="chat-toggle"
          aria-pressed={chatOpen}
          aria-controls="chat-panel"
          onClick={onToggleChat}
          className={`flex h-8 items-center gap-2 rounded-[3px] border px-3 text-[12.5px] font-medium transition-colors ${
            chatOpen
              ? "border-accent/60 bg-accent/10 text-accent"
              : "border-line-strong text-fg hover:border-accent/60 hover:text-accent"
          }`}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path
              d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinejoin="round"
            />
          </svg>
          ASISTENTE
        </button>
      </div>
    </header>
  );
}
