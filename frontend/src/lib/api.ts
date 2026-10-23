import type {
  ChatHistoryResponse,
  ChatMessage,
  Candle,
  Health,
  HistoryResponse,
  Portfolio,
  TradeResponse,
  TradeSide,
  PendingOrder,
  WatchlistResponse,
} from "./types";

/** Production is always same-origin; a developer's .env.local must not leak into the static export. */
export const API_BASE = process.env.NODE_ENV === "production" ? "" : (process.env.NEXT_PUBLIC_API_BASE ?? "");

export const PRICE_STREAM_URL = `${API_BASE}/api/stream/prices`;

/** A non-2xx response. `detail` is the backend's user-facing message. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

function describeDetail(detail: unknown, status: number): string {
  if (typeof detail === "string" && detail) return detail;
  // FastAPI 422s carry a list of {loc, msg}.
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: unknown };
    if (typeof first?.msg === "string") return first.msg;
  }
  return `Request failed (${status})`;
}

/** REST calls are sub-second; anything slower means the server is stuck. */
const DEFAULT_TIMEOUT_MS = 15_000;
/** The backend caps an LLM call at 30 s; leave room for the round trip. */
const CHAT_TIMEOUT_MS = 45_000;

/** Shared by the charla client (src/lib/charla/api.ts). */
export async function request<T>(path: string, init?: RequestInit, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: init?.body ? { "Content-Type": "application/json", ...init.headers } : init?.headers,
    });
  } catch {
    throw controller.signal.aborted
      ? new ApiError(0, "The server took too long to respond. Try again.")
      : new ApiError(0, "Can't reach the FinAlly server. Check that it is running.");
  } finally {
    clearTimeout(timer);
  }
  if (!response.ok) {
    let detail: unknown;
    try {
      detail = ((await response.json()) as { detail?: unknown }).detail;
    } catch {
      detail = undefined;
    }
    throw new ApiError(response.status, describeDetail(detail, response.status));
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("/api/health"),
  portfolio: () => request<Portfolio>("/api/portfolio"),
  history: (limit = 500) => request<HistoryResponse>(`/api/portfolio/history?limit=${limit}`),
  trade: (ticker: string, quantity: number, side: TradeSide) =>
    request<TradeResponse>("/api/portfolio/trade", {
      method: "POST",
      body: JSON.stringify({ ticker, quantity, side }),
    }),
  watchlist: () => request<WatchlistResponse>("/api/watchlist"),
  addToWatchlist: (ticker: string) =>
    request<WatchlistResponse>("/api/watchlist", {
      method: "POST",
      body: JSON.stringify({ ticker }),
    }),
  removeFromWatchlist: (ticker: string) =>
    request<WatchlistResponse>(`/api/watchlist/${encodeURIComponent(ticker)}`, {
      method: "DELETE",
    }),
  chat: (message: string, context?: { ticker?: string | null; timeframe?: string }) =>
    request<ChatMessage>(
      "/api/chat",
      {
        method: "POST",
        body: JSON.stringify({ message, ...context }),
      },
      CHAT_TIMEOUT_MS,
    ),
  chatHistory: (limit = 50) => request<ChatHistoryResponse>(`/api/chat/history?limit=${limit}`),
  candles: (ticker: string, timeframe: string, limit = 150) =>
    request<{ ticker: string; timeframe: string; candles: Candle[]; source: string; synthetic: boolean }>(
      `/api/market/candles?ticker=${encodeURIComponent(ticker)}&timeframe=${timeframe}&limit=${limit}`,
    ),
  order: (body: { ticker: string; side: TradeSide; type: "market" | "limit" | "stop"; notional: number; trigger_price?: number; stop_loss?: number; take_profit?: number; client_order_id?: string }) =>
    request<{ status: string; trade?: TradeResponse["trade"]; order?: PendingOrder; portfolio?: Portfolio }>("/api/orders", {
      method: "POST", body: JSON.stringify(body),
    }),
  cancelOrder: (id: string) => request<{ ok: boolean }>(`/api/orders/${encodeURIComponent(id)}`, { method: "DELETE" }),
  editOrder: (id: string, body: { trigger_price?: number; stop_loss?: number | null; take_profit?: number | null }) =>
    request<{ order: PendingOrder }>(`/api/orders/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(body) }),
  setRisk: (ticker: string, body: { stop_loss: number | null; take_profit: number | null }) =>
    request<{ ticker: string; stop_loss: number | null; take_profit: number | null }>(`/api/positions/${encodeURIComponent(ticker)}/risk`, { method: "PUT", body: JSON.stringify(body) }),
  closePosition: (ticker: string) => request<TradeResponse>(`/api/positions/${encodeURIComponent(ticker)}/close`, { method: "POST" }),
  workstation: () => request<Record<string, unknown>>("/api/workstation"),
};
