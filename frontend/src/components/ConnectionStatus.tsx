import type { ConnectionStatus as Status } from "@/lib/priceStore";

const LABEL: Record<Status, string> = {
  connected: "Live",
  reconnecting: "Reconnecting",
  disconnected: "Offline",
};

const DOT: Record<Status, string> = {
  connected: "bg-gain",
  reconnecting: "bg-accent status-pulse",
  disconnected: "bg-loss",
};

/** Green = streaming, yellow = EventSource is retrying, red = the stream gave up. */
export function ConnectionStatus({ status }: { status: Status }) {
  return (
    <div
      data-testid="connection-status"
      data-status={status}
      role="status"
      aria-label={`Prices: ${LABEL[status].toLowerCase()}`}
      title={`Prices: ${LABEL[status].toLowerCase()}`}
      className="flex items-center gap-1.5 text-[12px] text-muted"
    >
      <span className={`inline-block h-2 w-2 rounded-full ${DOT[status]}`} aria-hidden="true" />
      <span>{LABEL[status]}</span>
    </div>
  );
}
