import { expect, test, type Page } from '@playwright/test';
import {
  apiTrade,
  getPortfolio,
  getWatchlistTickers,
  openApp,
  openChat,
  positionQty,
  readNumber,
  removeTicker,
  uniqueToken,
} from './support/app';

// Mock-mode rules (CONTRACTS §7.3): "add T", "remove T", "buy N T", "sell N T"; tickers in uppercase.
const NO_MATCH_REPLY =
  'I\'m FinAlly, running in mock mode. Try "buy 1 AAPL", "sell 1 AAPL", "add PYPL" or "remove PYPL".';

/** Send a chat message; returns locators for the user message and the assistant reply that follows it. */
async function sendChat(page: Page, text: string) {
  await page.getByTestId('chat-input').fill(text);
  await page.getByTestId('chat-send-button').click();
  const userMessage = page.getByTestId('chat-message').filter({ hasText: text });
  await expect(userMessage).toHaveAttribute('data-role', 'user');
  const reply = userMessage.locator('xpath=following::*[@data-testid="chat-message"][1]');
  await expect(reply).toHaveAttribute('data-role', 'assistant');
  return { userMessage, reply };
}

test.describe('trade and watchlist actions', () => {
  const WATCH = 'PYPL';
  const TRADE = 'AAPL';
  let qtyBefore = 0;

  test.beforeEach(async ({ request }) => {
    await removeTicker(request, WATCH);
    qtyBefore = positionQty(await getPortfolio(request), TRADE);
  });

  test.afterEach(async ({ request }) => {
    await removeTicker(request, WATCH);
    const extra = positionQty(await getPortfolio(request), TRADE) - qtyBefore;
    if (extra > 0) await apiTrade(request, TRADE, 'sell', Number(extra.toFixed(4)));
  });

  test('executes them and shows each result inline', async ({ page, request }) => {
    await openApp(page);
    await openChat(page);

    const { reply } = await sendChat(page, `Please add ${WATCH} and buy 1 ${TRADE} (${uniqueToken()})`);
    await expect(reply).toContainText(`Adding ${WATCH} to your watchlist.`);
    await expect(reply).toContainText(`Placing a buy order for 1 ${TRADE}.`);

    const actions = reply.getByTestId('chat-action');
    await expect(actions).toHaveCount(2);
    const watchAction = actions.and(page.locator('[data-kind="watchlist"]'));
    const tradeAction = actions.and(page.locator('[data-kind="trade"]'));
    await expect(watchAction).toHaveAttribute('data-status', 'ok');
    await expect(watchAction).toContainText(WATCH);
    await expect(tradeAction).toHaveAttribute('data-status', 'ok');
    await expect(tradeAction).toContainText(TRADE);

    // The rest of the UI picks up the changes without a reload.
    await expect(page.getByTestId(`watchlist-row-${WATCH}`)).toBeVisible();
    await expect(page.getByTestId(`position-row-${TRADE}`)).toBeVisible();
    await expect.poll(() => readNumber(page.getByTestId(`position-qty-${TRADE}`))).toBeCloseTo(qtyBefore + 1, 4);
    expect(await getWatchlistTickers(request)).toContain(WATCH);
    expect(positionQty(await getPortfolio(request), TRADE)).toBeCloseTo(qtyBefore + 1, 4);
  });
});

test('a failed trade is reported inline and changes nothing', async ({ page, request }) => {
  const TICKER = 'NFLX';
  const before = await getPortfolio(request);
  const tooMany = Math.ceil(positionQty(before, TICKER)) + 1000;
  await openApp(page);
  await openChat(page);

  const { reply } = await sendChat(page, `sell ${tooMany} ${TICKER} (${uniqueToken()})`);
  await expect(reply).toContainText(`Placing a sell order for ${tooMany} ${TICKER}.`);
  const action = reply.getByTestId('chat-action');
  await expect(action).toHaveCount(1);
  await expect(action).toHaveAttribute('data-kind', 'trade');
  await expect(action).toHaveAttribute('data-status', 'failed');
  await expect(action).toContainText(/insufficient shares/i);

  const after = await getPortfolio(request);
  expect(after.cash_balance).toBe(before.cash_balance);
  expect(positionQty(after, TICKER)).toBe(positionQty(before, TICKER));
});

test('a message without actions gets the fixed mock reply', async ({ page }) => {
  await openApp(page);
  await openChat(page);

  const { reply } = await sendChat(page, `How is my portfolio doing? (${uniqueToken()})`);
  await expect(reply).toHaveText(new RegExp(NO_MATCH_REPLY.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  await expect(reply.getByTestId('chat-action')).toHaveCount(0);
});

test('an invalid trade quantity is reported as a failed action', async ({ page, request }) => {
  const before = await getPortfolio(request);
  await openApp(page);
  await openChat(page);

  const { reply } = await sendChat(page, `buy 0 AAPL (${uniqueToken()})`);
  const action = reply.getByTestId('chat-action');
  await expect(action).toHaveCount(1);
  await expect(action).toHaveAttribute('data-kind', 'trade');
  await expect(action).toHaveAttribute('data-status', 'failed');
  await expect(action).toContainText(/greater than 0/i);
  expect((await getPortfolio(request)).cash_balance).toBe(before.cash_balance);
});

test('an assistant outage shows an inline error', async ({ page }) => {
  await openApp(page);
  await openChat(page);
  // Mock mode never returns 502 (the retry-then-502 path is unit-tested in backend/tests/llm),
  // so stub the response to check how the panel presents it.
  await page.route('**/api/chat', (route) =>
    route.fulfill({
      status: 502,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'The AI assistant is unavailable right now. Please try again.' }),
    }),
  );

  await page.getByTestId('chat-input').fill(`Hello? (${uniqueToken()})`);
  await page.getByTestId('chat-send-button').click();
  await expect(page.getByTestId('chat-error')).toBeVisible();
  await expect(page.getByTestId('chat-error')).not.toBeEmpty();
  await expect(page.getByTestId('chat-loading')).toBeHidden();
});

test('shows a loading indicator while waiting for the reply', async ({ page }) => {
  await openApp(page);
  await openChat(page);
  // The mock answers instantly; hold the request so the indicator is observable.
  await page.route('**/api/chat', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1_500));
    await route.continue();
  });

  await page.getByTestId('chat-input').fill(`Hello there (${uniqueToken()})`);
  await page.getByTestId('chat-send-button').click();
  await expect(page.getByTestId('chat-loading')).toBeVisible();
  await expect(page.getByTestId('chat-loading')).toBeHidden({ timeout: 10_000 });
  await expect(page.getByTestId('chat-message').last()).toHaveAttribute('data-role', 'assistant');
});

test('conversation history is restored after a reload', async ({ page }) => {
  await openApp(page);
  await openChat(page);
  const text = `Remember this message (${uniqueToken()})`;
  await sendChat(page, text);

  await page.reload();
  await openChat(page);
  const restored = page.getByTestId('chat-message').filter({ hasText: text });
  await expect(restored).toHaveAttribute('data-role', 'user');
  await expect(restored.locator('xpath=following::*[@data-testid="chat-message"][1]')).toHaveAttribute(
    'data-role',
    'assistant',
  );
});
