import { expect, test } from '@playwright/test';

import { getPortfolio, openApp } from './support/app';

test('new ticket executes a market buy and retains it across reload', async ({ page, request }) => {
  await openApp(page);
  const before = await getPortfolio(request);
  const response = page.waitForResponse((item) => item.url().endsWith('/api/orders') && item.request().method() === 'POST');
  await page.getByRole('button', { name: 'COMPRAR AAPL' }).click();
  expect((await response).status()).toBe(200);
  await expect(page.getByTestId('position-row-AAPL')).toBeVisible();
  expect((await getPortfolio(request)).cash_balance).toBeLessThan(before.cash_balance);
  await page.reload();
  await expect(page.getByTestId('position-row-AAPL')).toBeVisible();
  await page.getByTestId('position-row-AAPL').getByRole('button', { name: 'CERRAR' }).click();
  await expect(page.getByTestId('position-row-AAPL')).toHaveCount(0);
});

test('prediction and sample sentiment leave account state unchanged', async ({ page, request }) => {
  await openApp(page);
  const before = await getPortfolio(request);
  await page.getByRole('button', { name: 'Detalles' }).click();
  await expect(page.getByText('DATOS DE MUESTRA · FUENTE SIMULADA')).toBeVisible();
  await expect(page.getByText(/No representa opiniones reales/)).toBeVisible();
  await page.getByRole('button', { name: 'PREDECIR' }).click();
  await expect(page.getByText('PREDECIR')).toBeVisible();
  await page.getByRole('button', { name: 'CERRAR' }).click();
  const after = await getPortfolio(request);
  expect(after.cash_balance).toBe(before.cash_balance);
  expect(after.positions).toEqual(before.positions);
});

test('desktop viewport guards and watchlist columns', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 810 });
  await openApp(page);
  const row = page.getByTestId('watchlist-row-AAPL');
  const change = page.getByTestId('watchlist-change-AAPL');
  const bounds = await row.boundingBox();
  const changeBounds = await change.boundingBox();
  expect(bounds).not.toBeNull();
  expect(changeBounds).not.toBeNull();
  expect(changeBounds!.x + changeBounds!.width).toBeLessThanOrEqual(bounds!.x + bounds!.width);
  await page.setViewportSize({ width: 1280, height: 720 });
  await expect(page.getByRole('heading', { name: 'Terminal de escritorio' })).toHaveCount(0);
  await page.setViewportSize({ width: 1100, height: 720 });
  await expect(page.getByRole('heading', { name: 'Terminal de escritorio' })).toBeVisible();
});
