"""Table definitions and seed data (CONTRACTS.md §6)."""

SCHEMA_VERSION = 3

USER_ID = "default"  # single user for now; every query filters on it
STARTING_CASH = 10_000.0
DEFAULT_WATCHLIST = ("AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users_profile (
  id TEXT PRIMARY KEY DEFAULT 'default',
  cash_balance REAL NOT NULL DEFAULT 10000.0,
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS watchlist (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'default', ticker TEXT NOT NULL,
  added_at TEXT NOT NULL, UNIQUE (user_id, ticker));
CREATE TABLE IF NOT EXISTS positions (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'default', ticker TEXT NOT NULL,
  quantity REAL NOT NULL, avg_cost REAL NOT NULL, updated_at TEXT NOT NULL, UNIQUE (user_id, ticker));
CREATE TABLE IF NOT EXISTS trades (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'default', ticker TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('buy', 'sell')), quantity REAL NOT NULL, price REAL NOT NULL,
  executed_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'default', total_value REAL NOT NULL,
  recorded_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_snapshots_user_time ON portfolio_snapshots (user_id, recorded_at);
CREATE TABLE IF NOT EXISTS chat_messages (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'default',
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')), content TEXT NOT NULL,
  actions TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_chat_user_time ON chat_messages (user_id, created_at);
CREATE TABLE IF NOT EXISTS price_marks (
  ticker TEXT PRIMARY KEY, price REAL NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pending_orders (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'default', client_order_id TEXT NOT NULL,
  ticker TEXT NOT NULL, side TEXT NOT NULL CHECK (side IN ('buy','sell')),
  type TEXT NOT NULL CHECK (type IN ('limit','stop')), notional REAL NOT NULL,
  trigger_price REAL NOT NULL, stop_loss REAL, take_profit REAL, trade_id TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','filled','cancelled','rejected')),
  reason TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(user_id, client_order_id));
CREATE INDEX IF NOT EXISTS idx_pending_orders_status ON pending_orders(user_id, status, created_at);
CREATE TABLE IF NOT EXISTS market_order_requests (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'default', client_order_id TEXT NOT NULL,
  ticker TEXT NOT NULL, side TEXT NOT NULL CHECK (side IN ('buy','sell')),
  notional REAL NOT NULL, trade_id TEXT, status TEXT NOT NULL CHECK (status IN ('pending','filled','rejected')),
  reason TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(user_id, client_order_id));
CREATE TABLE IF NOT EXISTS position_risk (
  user_id TEXT NOT NULL DEFAULT 'default', ticker TEXT NOT NULL,
  stop_loss REAL, take_profit REAL, updated_at TEXT NOT NULL,
  PRIMARY KEY(user_id, ticker));
CREATE TABLE IF NOT EXISTS activity_events (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'default', kind TEXT NOT NULL,
  ticker TEXT, message TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_activity_user_time ON activity_events(user_id, created_at);
""" + """
-- Live talk ("charla", planning/charla/CONTRACT.md §3). *_at are ISO strings; *_ms are epoch ms.
CREATE TABLE IF NOT EXISTS charla_attendees (
  id TEXT PRIMARY KEY,
  username TEXT NOT NULL,
  username_key TEXT NOT NULL UNIQUE,
  email TEXT NOT NULL UNIQUE,
  verified_at TEXT,
  link_hash TEXT,
  link_expires_at TEXT,
  link_sent_at TEXT,
  sends_count INTEGER NOT NULL DEFAULT 0,
  sends_window_start TEXT,
  pending_hash TEXT,
  pending_approved_at TEXT,
  phone TEXT,
  phone_consent_at TEXT,
  phone_skipped_at TEXT,
  hidden INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_charla_attendees_link ON charla_attendees (link_hash);
CREATE INDEX IF NOT EXISTS idx_charla_attendees_pending ON charla_attendees (pending_hash);
CREATE TABLE IF NOT EXISTS charla_sessions (
  id TEXT PRIMARY KEY,
  attendee_id TEXT NOT NULL REFERENCES charla_attendees (id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS charla_answers (
  id TEXT PRIMARY KEY,
  attendee_id TEXT NOT NULL REFERENCES charla_attendees (id) ON DELETE CASCADE,
  step INTEGER NOT NULL,
  choice INTEGER,
  open_text TEXT,
  theme TEXT,
  correct INTEGER NOT NULL DEFAULT 0,
  points INTEGER NOT NULL DEFAULT 0,
  ms INTEGER NOT NULL,
  hidden INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  UNIQUE (attendee_id, step));
CREATE INDEX IF NOT EXISTS idx_charla_answers_step ON charla_answers (step);
CREATE TABLE IF NOT EXISTS charla_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  step INTEGER NOT NULL DEFAULT 0,
  phase TEXT NOT NULL DEFAULT 'idle' CHECK (phase IN ('idle', 'open', 'closed', 'revealed')),
  opened_at_ms INTEGER,
  deadline_ms INTEGER,
  verification_on INTEGER NOT NULL DEFAULT 1,
  phone_prompt INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL);
"""
