import { expect, test, type Page } from '@playwright/test';
import { getPortfolio, getWatchlist, openApp, positionQty, readNumber, watchlistRows } from './support/app';

// In simulator mode every well-formed symbol is tradeable (the simulator invents a price for it),
// so the "unknown ticker" path is exercised with malformed symbols here. Massive-only
// "Unknown ticker: XYZ" errors are covered by backend unit tests.
const MALFORMED = '1234';

async function tradeBar(page: Page, ticker: string, quantity: number | string, side: 'buy' | 'sell') {
  await page.getByTestId('trade-ticker-input').fill(ticker);
  await page.getByTestId('trade-quantity-input').fill(String(quantity));
  await page.getByTestId(side === 'buy' ? 'trade-buy-button' : 'trade-sell-button').click();
}

test('buying more than the cash allows shows an error and changes nothing', async ({ page, request }) => {
  const TICKER = 'NFLX';
  const before = await getPortfolio(request);
  const quote = (await getWatchlist(request)).find((w) => w.ticker === TICKER)?.quote;
  expect(quote, `${TICKER} should be priced`).toBeTruthy();
  const quantity = Math.ceil((before.cash_balance * 2) / quote!.price);
  await openApp(page);

  await tradeBar(page, TICKER, quantity, 'buy');
  const message = page.getByTestId('trade-message');
  await expect(message).toHaveAttribute('data-status', 'error');
  await expect(message).toContainText(/insufficient cash/i);

  const after = await getPortfolio(request);
  expect(after.cash_balance).toBe(before.cash_balance);
  expect(positionQty(after, TICKER)).toBe(positionQty(before, TICKER));
  await expect.poll(() => readNumber(page.getByTestId('header-cash'))).toBeCloseTo(before.cash_balance, 2);
});

test('selling more shares than held shows an error and changes nothing', async ({ page, request }) => {
  const TICKER = 'V';
  const before = await getPortfolio(request);
  const quantity = Math.ceil(positionQty(before, TICKER)) + 1000;
  await openApp(page);

  await tradeBar(page, TICKER, quantity, 'sell');
  const message = page.getByTestId('trade-message');
  await expect(message).toHaveAttribute('data-status', 'error');
  await expect(message).toContainText(/insufficient shares/i);

  const after = await getPortfolio(request);
  expect(after.cash_balance).toBe(before.cash_balance);
  expect(positionQty(after, TICKER)).toBe(positionQty(before, TICKER));
});

test('the trade bar rejects a malformed ticker', async ({ page, request }) => {
  const before = await getPortfolio(request);
  await openApp(page);

  await tradeBar(page, MALFORMED, 1, 'buy');
  await expect(page.getByTestId('trade-message')).toHaveAttribute('data-status', 'error');

  const after = await getPortfolio(request);
  expect(after.cash_balance).toBe(before.cash_balance);
  expect(after.positions.length).toBe(before.positions.length);
});

test('the watchlist rejects a malformed ticker', async ({ page, request }) => {
  await openApp(page);
  const rows = watchlistRows(page);
  const countBefore = await rows.count();
  const tickersBefore = (await getWatchlist(request)).map((w) => w.ticker);

  await page.getByTestId('watchlist-add-input').fill(MALFORMED);
  await page.getByTestId('watchlist-add-button').click();
  await expect(page.getByTestId('watchlist-error')).toBeVisible();
  await expect(page.getByTestId('watchlist-error')).not.toBeEmpty();

  await expect(rows).toHaveCount(countBefore);
  expect((await getWatchlist(request)).map((w) => w.ticker)).toEqual(tickersBefore);
});

test('the trade bar rejects a zero quantity', async ({ page, request }) => {
  const before = await getPortfolio(request);
  await openApp(page);

  await tradeBar(page, 'AAPL', 0, 'buy');
  await expect(page.getByTestId('trade-message')).toHaveAttribute('data-status', 'error');
  expect((await getPortfolio(request)).cash_balance).toBe(before.cash_balance);
});
