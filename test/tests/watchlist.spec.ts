import { expect, test } from '@playwright/test';
import { dataPoints, getWatchlistTickers, openApp, readNumber, removeTicker, watchlistRows } from './support/app';

const TICKER = 'DIS'; // not in the default watchlist; used only by this file

test.beforeEach(async ({ request }) => {
  await removeTicker(request, TICKER);
});

test.afterEach(async ({ request }) => {
  await removeTicker(request, TICKER);
});

test('adds a ticker that starts streaming, keeps it across reloads, then removes it', async ({ page, request }) => {
  await openApp(page);
  const rows = watchlistRows(page);
  const countBefore = await rows.count();

  await page.getByTestId('watchlist-add-input').fill(TICKER.toLowerCase());
  await page.getByTestId('watchlist-add-button').click();

  const row = page.getByTestId(`watchlist-row-${TICKER}`);
  await expect(row).toBeVisible();
  await expect(rows).toHaveCount(countBefore + 1);
  await expect.poll(() => readNumber(page.getByTestId(`watchlist-price-${TICKER}`))).toBeGreaterThan(0);
  await expect.poll(() => dataPoints(page.getByTestId(`sparkline-${TICKER}`))).toBeGreaterThanOrEqual(2);
  expect(await getWatchlistTickers(request)).toContain(TICKER);

  await page.reload();
  await expect(row).toBeVisible();

  await page.getByTestId(`watchlist-remove-${TICKER}`).click();
  await expect(row).toHaveCount(0);
  await expect(rows).toHaveCount(countBefore);
  expect(await getWatchlistTickers(request)).not.toContain(TICKER);
});

test('clicking a ticker selects it for the main chart and pre-fills the trade bar', async ({ page }) => {
  await openApp(page);

  for (const ticker of ['MSFT', 'NVDA']) {
    await page.getByTestId(`watchlist-row-${ticker}`).click();
    await expect(page.getByTestId('main-chart')).toHaveAttribute('data-ticker', ticker);
    await expect(page.getByTestId('trade-ticker-input')).toHaveValue(ticker);
  }
});
