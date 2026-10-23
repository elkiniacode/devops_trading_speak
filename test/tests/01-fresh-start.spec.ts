import { expect, test } from '@playwright/test';
import {
  DEFAULT_TICKERS,
  dataPoints,
  expectPricesToMove,
  getPortfolio,
  getWatchlistTickers,
  parseNumber,
  positionRows,
  readNumber,
  watchlistRows,
} from './support/app';

// Needs the untouched seed DB: the local runner and docker-compose.test.yml both start one per run,
// and this file sorts first (single worker, alphabetical file order). Nothing else depends on it.

test('server starts from the seed in mock/simulator mode', async ({ request }) => {
  const health = await (await request.get('/api/health')).json();
  expect(health).toMatchObject({ status: 'ok', market_data: 'simulator', llm: 'mock' });

  const portfolio = await getPortfolio(request);
  expect(portfolio.cash_balance, 'fresh DB should hold $10,000 (is the server reused from an earlier run?)').toBe(
    10000,
  );
  expect(portfolio.positions).toEqual([]);
  expect(portfolio.total_value).toBe(10000);
  expect((await getWatchlistTickers(request)).sort()).toEqual([...DEFAULT_TICKERS].sort());
});

test('shows the default watchlist, $10,000 and live prices', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByTestId('connection-status')).toHaveAttribute('data-status', 'connected');
  await expect(watchlistRows(page)).toHaveCount(DEFAULT_TICKERS.length);
  for (const ticker of DEFAULT_TICKERS) {
    await expect(page.getByTestId(`watchlist-row-${ticker}`)).toBeVisible();
    await expect(page.getByTestId(`watchlist-price-${ticker}`)).toHaveText(/\d/);
    await expect(page.getByTestId(`watchlist-change-${ticker}`)).toHaveText(/\d/);
    await expect(page.getByTestId(`watchlist-row-${ticker}`)).toHaveAttribute('data-direction', /^(up|down|flat)$/);
  }

  await expect.poll(() => readNumber(page.getByTestId('header-cash'))).toBe(10000);
  await expect.poll(() => readNumber(page.getByTestId('header-total-value'))).toBe(10000);
  await expect(page.getByTestId('header-cash')).toHaveText(/10,000\.00/);

  await expect(positionRows(page)).toHaveCount(0);
  await page.getByRole('button', { name: 'MERCADOS' }).click();
  await expect(page.getByTestId('heatmap-empty')).toBeVisible();
  await expect.poll(() => dataPoints(page.getByTestId('pnl-chart'))).toBeGreaterThanOrEqual(1);
  await expect(page.getByTestId('chat-panel').or(page.getByTestId('chat-toggle')).first()).toBeVisible();

  // Prices stream: values change, sparklines grow, rows flash.
  await expectPricesToMove(page);
  const sparkline = page.getByTestId('sparkline-AAPL');
  const points = await dataPoints(sparkline);
  await expect.poll(() => dataPoints(sparkline)).toBeGreaterThanOrEqual(points + 2);
  await expect(page.locator('.flash-up, .flash-down').first()).toBeAttached({ timeout: 5_000 });

  // Every price shown is a plausible dollar amount.
  for (const ticker of DEFAULT_TICKERS) {
    const price = parseNumber(await page.getByTestId(`watchlist-price-${ticker}`).innerText());
    expect(price, `${ticker} price`).toBeGreaterThan(1);
  }
});
