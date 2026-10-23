import { expect, test } from '@playwright/test';
import {
  apiTrade,
  closePosition,
  dataPoints,
  getPortfolio,
  getWatchlistTickers,
  openApp,
  readNumber,
  submitTrade,
  type Portfolio,
  type Trade,
} from './support/app';

// Each test owns one ticker, starts without a position in it and closes it again afterwards.

test.describe('buy', () => {
  const TICKER = 'MSFT';
  test.beforeEach(({ request }) => closePosition(request, TICKER));
  test.afterEach(({ request }) => closePosition(request, TICKER));

  test('cash decreases, the position appears and the portfolio updates', async ({ page, request }) => {
    const before = await getPortfolio(request);
    await openApp(page);
    const pnlChart = page.getByTestId('pnl-chart');
    await expect.poll(() => dataPoints(pnlChart)).toBeGreaterThanOrEqual(1);
    const snapshotsBefore = await dataPoints(pnlChart);

    const response = await submitTrade(page, TICKER, 2, 'buy');
    expect(response.status()).toBe(200);
    const { trade, portfolio } = (await response.json()) as { trade: Trade; portfolio: Portfolio };
    expect(trade).toMatchObject({ ticker: TICKER, side: 'buy', quantity: 2 });
    expect(trade.total).toBeCloseTo(trade.price * 2, 2);
    expect(portfolio.cash_balance).toBeCloseTo(before.cash_balance - trade.total, 2);

    await expect(page.getByTestId('trade-message')).toHaveAttribute('data-status', 'success');
    await expect.poll(() => readNumber(page.getByTestId('header-cash'))).toBeCloseTo(portfolio.cash_balance, 2);

    await expect(page.getByTestId(`position-row-${TICKER}`)).toBeVisible();
    await expect.poll(() => readNumber(page.getByTestId(`position-qty-${TICKER}`))).toBe(2);
    await expect.poll(() => readNumber(page.getByTestId(`position-avg-cost-${TICKER}`))).toBeCloseTo(trade.price, 2);
    await expect.poll(() => readNumber(page.getByTestId(`position-price-${TICKER}`))).toBeGreaterThan(0);
    await expect(page.getByTestId(`heatmap-tile-${TICKER}`)).toBeVisible();
    await expect(page.getByTestId('heatmap-empty')).toHaveCount(0);

    // A market buy converts cash into shares at the market price: total value barely moves.
    const total = await readNumber(page.getByTestId('header-total-value'));
    expect(Math.abs(total - portfolio.total_value)).toBeLessThan(portfolio.total_value * 0.01);

    // A snapshot is recorded after every trade and the P&L chart refetches it.
    await expect.poll(() => dataPoints(pnlChart)).toBeGreaterThan(snapshotsBefore);
  });
});

test.describe('sell', () => {
  const TICKER = 'JPM';
  test.beforeEach(async ({ request }) => {
    await closePosition(request, TICKER);
    await apiTrade(request, TICKER, 'buy', 3);
  });
  test.afterEach(({ request }) => closePosition(request, TICKER));

  test('cash increases, the position shrinks and then disappears', async ({ page, request }) => {
    await openApp(page);
    const row = page.getByTestId(`position-row-${TICKER}`);
    await expect(row).toBeVisible();
    const before = await getPortfolio(request);

    let response = await submitTrade(page, TICKER, 1, 'sell');
    expect(response.status()).toBe(200);
    let body = (await response.json()) as { trade: Trade; portfolio: Portfolio };
    expect(body.trade).toMatchObject({ ticker: TICKER, side: 'sell', quantity: 1 });
    expect(body.portfolio.cash_balance).toBeCloseTo(before.cash_balance + body.trade.total, 2);
    await expect(page.getByTestId('trade-message')).toHaveAttribute('data-status', 'success');
    await expect.poll(() => readNumber(page.getByTestId('header-cash'))).toBeCloseTo(body.portfolio.cash_balance, 2);
    await expect.poll(() => readNumber(page.getByTestId(`position-qty-${TICKER}`))).toBe(2);

    response = await submitTrade(page, TICKER, 2, 'sell');
    expect(response.status()).toBe(200);
    body = (await response.json()) as { trade: Trade; portfolio: Portfolio };
    expect(body.portfolio.positions.map((p) => p.ticker)).not.toContain(TICKER);
    await expect(row).toHaveCount(0);
    await expect(page.getByTestId(`heatmap-tile-${TICKER}`)).toHaveCount(0);
    await expect.poll(() => readNumber(page.getByTestId('header-cash'))).toBeCloseTo(body.portfolio.cash_balance, 2);
    // JPM is on the default watchlist, so it keeps streaming after the position closes.
    await expect(page.getByTestId(`watchlist-row-${TICKER}`)).toBeVisible();
  });
});

test.describe('ticker not on the watchlist', () => {
  const TICKER = 'ORCL';
  test.beforeEach(({ request }) => closePosition(request, TICKER));
  test.afterEach(({ request }) => closePosition(request, TICKER));

  test('can be bought from the trade bar, is priced while held and sold again', async ({ page, request }) => {
    expect(await getWatchlistTickers(request)).not.toContain(TICKER);
    await openApp(page);

    let response = await submitTrade(page, TICKER, 1, 'buy');
    expect(response.status()).toBe(200);
    await expect(page.getByTestId(`position-row-${TICKER}`)).toBeVisible();
    await expect.poll(() => readNumber(page.getByTestId(`position-price-${TICKER}`))).toBeGreaterThan(0);
    await expect(page.getByTestId(`heatmap-tile-${TICKER}`)).toBeVisible();

    response = await submitTrade(page, TICKER, 1, 'sell');
    expect(response.status()).toBe(200);
    await expect(page.getByTestId(`position-row-${TICKER}`)).toHaveCount(0);
    expect(await getWatchlistTickers(request)).not.toContain(TICKER);
  });
});
