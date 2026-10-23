import { expect, type APIRequestContext, type APIResponse, type Locator, type Page } from '@playwright/test';

/** Seeded watchlist (CONTRACTS §6). */
export const DEFAULT_TICKERS = ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA', 'NVDA', 'META', 'JPM', 'V', 'NFLX'];

export interface Quote {
  ticker: string;
  price: number;
  previous_price: number;
  reference_price: number;
  change: number;
  change_percent: number;
  direction: 'up' | 'down' | 'flat';
  timestamp: string;
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

export interface Trade {
  id: string;
  ticker: string;
  side: 'buy' | 'sell';
  quantity: number;
  price: number;
  total: number;
  executed_at: string;
}

// ---------------------------------------------------------------------------------------------
// REST helpers: set up and inspect state directly, so each test can arrange its own preconditions.

async function json<T>(response: APIResponse, what: string): Promise<T> {
  if (!response.ok()) throw new Error(`${what} failed: HTTP ${response.status()} ${await response.text()}`);
  return (await response.json()) as T;
}

export async function getPortfolio(request: APIRequestContext): Promise<Portfolio> {
  return json<Portfolio>(await request.get('/api/portfolio'), 'GET /api/portfolio');
}

export async function getWatchlist(request: APIRequestContext): Promise<{ ticker: string; quote: Quote | null }[]> {
  const body = await json<{ watchlist: { ticker: string; quote: Quote | null }[] }>(
    await request.get('/api/watchlist'),
    'GET /api/watchlist',
  );
  return body.watchlist;
}

export async function getWatchlistTickers(request: APIRequestContext): Promise<string[]> {
  return (await getWatchlist(request)).map((item) => item.ticker);
}

export async function addTicker(request: APIRequestContext, ticker: string): Promise<void> {
  await json(await request.post('/api/watchlist', { data: { ticker } }), `POST /api/watchlist ${ticker}`);
}

export async function removeTicker(request: APIRequestContext, ticker: string): Promise<void> {
  await json(await request.delete(`/api/watchlist/${ticker}`), `DELETE /api/watchlist/${ticker}`);
}

export async function apiTrade(
  request: APIRequestContext,
  ticker: string,
  side: 'buy' | 'sell',
  quantity: number,
): Promise<{ trade: Trade; portfolio: Portfolio }> {
  return json(
    await request.post('/api/portfolio/trade', { data: { ticker, side, quantity } }),
    `${side} ${quantity} ${ticker}`,
  );
}

export function positionQty(portfolio: Portfolio, ticker: string): number {
  return portfolio.positions.find((p) => p.ticker === ticker)?.quantity ?? 0;
}

/** Sell the whole position in `ticker`, if any. */
export async function closePosition(request: APIRequestContext, ticker: string): Promise<void> {
  const qty = positionQty(await getPortfolio(request), ticker);
  if (qty > 0) await apiTrade(request, ticker, 'sell', qty);
}

// ---------------------------------------------------------------------------------------------
// Reading numbers from the UI. Tolerates "$1,234.56", "+0.33%", "-$1.20", "−1.20" and "($1.20)".

export function parseNumber(text: string): number {
  const normalized = text.replace(/−/g, '-');
  const match = normalized.match(/\d[\d,]*(?:\.\d+)?|\.\d+/);
  if (!match || match.index === undefined) throw new Error(`No number in ${JSON.stringify(text)}`);
  const value = Number(match[0].replace(/,/g, ''));
  const prefix = normalized.slice(0, match.index);
  return /[-(]/.test(prefix) ? -value : value;
}

export async function readNumber(locator: Locator): Promise<number> {
  return parseNumber(await locator.innerText());
}

export async function dataPoints(locator: Locator): Promise<number> {
  return Number((await locator.getAttribute('data-points')) ?? 'NaN');
}

export const watchlistRows = (page: Page) => page.locator('[data-testid^="watchlist-row-"]');
export const positionRows = (page: Page) => page.locator('[data-testid^="position-row-"]');
export const heatmapTiles = (page: Page) => page.locator('[data-testid^="heatmap-tile-"]');

/** Text of every watchlist price, keyed by ticker. */
export async function watchlistPrices(page: Page): Promise<Record<string, string>> {
  return page.evaluate(() => {
    const out: Record<string, string> = {};
    for (const el of document.querySelectorAll<HTMLElement>('[data-testid^="watchlist-price-"]')) {
      out[el.dataset.testid!.slice('watchlist-price-'.length)] = el.innerText;
    }
    return out;
  });
}

/** Wait until at least one watchlist price differs from what it shows now. */
export async function expectPricesToMove(page: Page, timeout = 10_000): Promise<void> {
  const before = await watchlistPrices(page);
  await expect
    .poll(
      async () => {
        const now = await watchlistPrices(page);
        return Object.keys(now).filter((t) => t in before && now[t] !== before[t]).length;
      },
      { timeout, message: 'expected a watchlist price to change (is the SSE stream flowing?)' },
    )
    .toBeGreaterThan(0);
}

// ---------------------------------------------------------------------------------------------
// Page actions

/** Load the app and wait until prices are streaming and the portfolio has loaded. */
export async function openApp(page: Page): Promise<void> {
  await page.goto('/');
  await expect(page.getByTestId('connection-status')).toHaveAttribute('data-status', 'connected');
  await expect(watchlistRows(page).first()).toBeVisible();
  await expect(page.getByTestId('header-cash')).toHaveText(/\d/);
}

export async function openChat(page: Page): Promise<void> {
  const input = page.getByTestId('chat-input');
  if (!(await input.isVisible())) await page.getByTestId('chat-toggle').click();
  await expect(input).toBeVisible();
}

/** Fill the trade bar and click buy or sell. Resolves with the trade API response. */
export async function submitTrade(page: Page, ticker: string, quantity: number | string, side: 'buy' | 'sell') {
  await page.getByTestId('trade-ticker-input').fill(ticker);
  await page.getByTestId('trade-quantity-input').fill(String(quantity));
  const response = page.waitForResponse(
    (r) => r.url().includes('/api/portfolio/trade') && r.request().method() === 'POST',
  );
  await page.getByTestId(side === 'buy' ? 'trade-buy-button' : 'trade-sell-button').click();
  return response;
}

/** A token that makes a chat message unique on the page (contains no mock-mode keywords). */
export function uniqueToken(): string {
  return `ref-${Date.now().toString(36)}`;
}
