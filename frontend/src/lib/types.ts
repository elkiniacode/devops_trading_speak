// Wire types for the backend API (planning/CONTRACTS.md §5, MARKET_INTERFACE.md §9).

export type Direction = "up" | "down" | "flat";

export interface PriceUpdate {
  ticker: string;
  price: number;
  previous_price: number;
  reference_price: number;
  change: number;
  change_percent: number;
  direction: Direction;
  timestamp: string; // ISO-8601 UTC
}

export type PriceMap = Record<string, PriceUpdate>;

export type MarketMode = "simulator" | "massive-snapshot" | "massive-eod";

export interface Health {
  status: string;
  market_data: MarketMode;
  llm: "mock" | "openrouter" | "unconfigured";
}

export interface WatchlistItem {
  ticker: string;
  added_at: string;
  quote: PriceUpdate | null;
}

export interface WatchlistResponse {
  watchlist: WatchlistItem[];
}

export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number | null;
  market_value: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_percent: number | null;
  stale: boolean;
}

export interface Portfolio {
  cash_balance: number;
  positions: Position[];
  positions_value: number;
  total_value: number;
  total_pnl: number;
  total_pnl_percent: number;
  valuation_complete: boolean;
  as_of: string;
}

export type TradeSide = "buy" | "sell";

export interface Trade {
  id: string;
  ticker: string;
  side: TradeSide;
  quantity: number;
  price: number;
  total: number;
  executed_at: string;
}

export interface TradeResponse {
  trade: Trade;
  portfolio: Portfolio;
}

export interface Snapshot {
  total_value: number;
  recorded_at: string;
}

export interface HistoryResponse {
  snapshots: Snapshot[];
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface PendingOrder {
  id: string;
  ticker: string;
  side: TradeSide;
  type: "limit" | "stop";
  notional: number;
  trigger_price: number;
  stop_loss: number | null;
  take_profit: number | null;
  status: "pending" | "filled" | "cancelled" | "rejected";
  reason: string | null;
  created_at: string;
}

export type ActionStatus = "ok" | "failed";

export interface TradeAction {
  ticker: string;
  side: TradeSide;
  quantity: number;
  status: ActionStatus;
  price: number | null;
  error: string | null;
}

export interface WatchlistAction {
  ticker: string;
  action: "add" | "remove";
  status: ActionStatus;
  error: string | null;
}

export interface ChatActions {
  watchlist_changes: WatchlistAction[];
  trades: TradeAction[];
  orders?: Array<{ ticker: string; side: TradeSide; type: "market" | "limit" | "stop"; status: ActionStatus; order_status?: string; error: string | null }>;
  closes?: Array<{ ticker: string; status: ActionStatus; error: string | null }>;
  risks?: Array<{ ticker: string; status: ActionStatus; error: string | null }>;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  actions: ChatActions | null;
  created_at: string;
}

export interface ChatHistoryResponse {
  messages: ChatMessage[];
}
