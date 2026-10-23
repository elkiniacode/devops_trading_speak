import { expect, test } from '@playwright/test';
import { addTicker, apiTrade, closePosition, getWatchlistTickers, removeTicker } from './support/app';

// Contract checks against the REST/SSE API (CONTRACTS §5). They pinpoint backend bugs that the
// UI specs would only show indirectly.

const ISO_UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;

test('GET /api/health', async ({ request }) => {
  const response = await request.get('/api/health');
  expect(response.status()).toBe(200);
  expect(await response.json()).toMatchObject({ status: 'ok', market_data: 'simulator', llm: 'mock' });
});

test('GET /api/watchlist returns priced rows', async ({ request }) => {
  const body = await (await request.get('/api/watchlist')).json();
  expect(Array.isArray(body.watchlist)).toBe(true);
  expect(body.watchlist.length).toBeGreaterThan(0);
  for (const item of body.watchlist) {
    expect(item.added_at).toMatch(ISO_UTC);
    expect(item.quote).toMatchObject({
      ticker: item.ticker,
      price: expect.any(Number),
      previous_price: expect.any(Number),
      reference_price: expect.any(Number),
      change: expect.any(Number),
      change_percent: expect.any(Number),
      direction: expect.stringMatching(/^(up|down|flat)$/),
      timestamp: expect.stringMatching(ISO_UTC),
    });
  }
});

test('watchlist add and remove are idempotent and normalize case', async ({ request }) => {
  const TICKER = 'WMT';
  await removeTicker(request, TICKER);
  try {
    for (let i = 0; i < 2; i++) {
      const response = await request.post('/api/watchlist', { data: { ticker: TICKER.toLowerCase() } });
      expect(response.status()).toBe(200);
      const tickers = (await response.json()).watchlist.map((w: { ticker: string }) => w.ticker);
      expect(tickers.filter((t: string) => t === TICKER)).toHaveLength(1);
    }
    for (let i = 0; i < 2; i++) {
      const response = await request.delete(`/api/watchlist/${TICKER}`);
      expect(response.status()).toBe(200);
      expect((await response.json()).watchlist.map((w: { ticker: string }) => w.ticker)).not.toContain(TICKER);
    }
  } finally {
    await removeTicker(request, TICKER);
  }
});

test('watchlist rejects a malformed ticker with 400', async ({ request }) => {
  const response = await request.post('/api/watchlist', { data: { ticker: 'A$' } });
  expect(response.status()).toBe(400);
  expect((await response.json()).detail).toMatch(/invalid ticker/i);
  expect(await getWatchlistTickers(request)).not.toContain('A$');
});

test('GET /api/portfolio shape', async ({ request }) => {
  const body = await (await request.get('/api/portfolio')).json();
  expect(body).toMatchObject({
    cash_balance: expect.any(Number),
    positions: expect.any(Array),
    positions_value: expect.any(Number),
    total_value: expect.any(Number),
    total_pnl: expect.any(Number),
    total_pnl_percent: expect.any(Number),
    valuation_complete: expect.any(Boolean),
    as_of: expect.stringMatching(ISO_UTC),
  });
  expect(body.total_value).toBeCloseTo(body.cash_balance + body.positions_value, 2);
  expect(body.total_pnl).toBeCloseTo(body.total_value - 10000, 2);
});

test('trade round trip returns the trade and the updated portfolio', async ({ request }) => {
  const TICKER = 'INTC';
  await closePosition(request, TICKER);
  try {
    const { trade, portfolio } = await apiTrade(request, TICKER, 'buy', 1.5);
    expect(trade).toMatchObject({ ticker: TICKER, side: 'buy', quantity: 1.5, executed_at: expect.stringMatching(ISO_UTC) });
    expect(trade.total).toBeCloseTo(trade.price * 1.5, 2);
    const position = portfolio.positions.find((p) => p.ticker === TICKER)!;
    expect(position).toMatchObject({ quantity: 1.5, stale: false });
    expect(position.avg_cost).toBeCloseTo(trade.price, 4);

    const sold = await apiTrade(request, TICKER, 'sell', 1.5);
    expect(sold.trade).toMatchObject({ ticker: TICKER, side: 'sell', quantity: 1.5 });
    expect(sold.portfolio.positions.map((p) => p.ticker)).not.toContain(TICKER);
  } finally {
    await closePosition(request, TICKER);
  }
});

test('trade validation errors are 400 with a readable detail', async ({ request }) => {
  const cases: [Record<string, unknown>, RegExp][] = [
    [{ ticker: 'A$', side: 'buy', quantity: 1 }, /invalid ticker/i],
    [{ ticker: 'AAPL', side: 'buy', quantity: 0 }, /greater than 0/i],
    [{ ticker: 'AAPL', side: 'buy', quantity: 1.23456 }, /4 decimal/i],
    [{ ticker: 'AAPL', side: 'hold', quantity: 1 }, /side/i],
    [{ ticker: 'AAPL', side: 'buy', quantity: 1_000 }, /insufficient cash/i],
    [{ ticker: 'AAPL', side: 'sell', quantity: 100_000 }, /insufficient shares/i],
  ];
  for (const [data, detail] of cases) {
    const response = await request.post('/api/portfolio/trade', { data });
    expect(response.status(), JSON.stringify(data)).toBe(400);
    expect((await response.json()).detail, JSON.stringify(data)).toMatch(detail);
  }
});

test('GET /api/portfolio/history is ascending and honors limit', async ({ request }) => {
  const body = await (await request.get('/api/portfolio/history')).json();
  expect(body.snapshots.length).toBeGreaterThanOrEqual(1);
  const times = body.snapshots.map((s: { recorded_at: string }) => s.recorded_at);
  expect(times).toEqual([...times].sort());
  for (const s of body.snapshots) {
    expect(s).toMatchObject({ total_value: expect.any(Number), recorded_at: expect.stringMatching(ISO_UTC) });
  }
  const limited = await (await request.get('/api/portfolio/history?limit=1')).json();
  expect(limited.snapshots).toHaveLength(1);
  expect(limited.snapshots[0]).toEqual(body.snapshots[body.snapshots.length - 1]);
});

test('chat validates input and exposes history', async ({ request }) => {
  const empty = await request.post('/api/chat', { data: { message: '   ' } });
  expect(empty.status()).toBe(400);

  const reply = await (await request.post('/api/chat', { data: { message: 'hello from the API spec' } })).json();
  expect(reply).toMatchObject({
    id: expect.any(String),
    role: 'assistant',
    content: expect.any(String),
    actions: { watchlist_changes: [], trades: [] },
    created_at: expect.stringMatching(ISO_UTC),
  });

  const history = await (await request.get('/api/chat/history?limit=2')).json();
  expect(history.messages).toHaveLength(2);
  expect(history.messages[0]).toMatchObject({ role: 'user', content: 'hello from the API spec', actions: null });
  expect(history.messages[1]).toMatchObject({ role: 'assistant', id: reply.id });
});

test('a rejected chat trade is a failed action in a 200 reply and changes nothing', async ({ request }) => {
  const text = `buy 0 AAPL (api-failed-${Date.now()})`;
  const before = (await (await request.get('/api/portfolio')).json()).cash_balance;
  const response = await request.post('/api/chat', { data: { message: text } });
  expect(response.status()).toBe(200);
  const reply = await response.json();
  expect(reply.actions.watchlist_changes).toEqual([]);
  expect(reply.actions.trades).toHaveLength(1);
  expect(reply.actions.trades[0]).toMatchObject({
    ticker: 'AAPL',
    side: 'buy',
    status: 'failed',
    price: null,
    error: expect.stringMatching(/greater than 0/i),
  });
  expect((await (await request.get('/api/portfolio')).json()).cash_balance).toBe(before);

  const history = await (await request.get('/api/chat/history?limit=2')).json();
  expect(history.messages[0]).toMatchObject({ role: 'user', content: text, actions: null });
  expect(history.messages[1]).toMatchObject({ role: 'assistant', id: reply.id, actions: reply.actions });
});

test('SSE sends a full price map immediately on connect', async ({ baseURL }) => {
  const controller = new AbortController();
  const started = Date.now();
  const response = await fetch(`${baseURL}/api/stream/prices`, { signal: controller.signal });
  expect(response.status).toBe(200);
  expect(response.headers.get('content-type')).toContain('text/event-stream');

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let data: string | undefined;
  try {
    while (data === undefined && Date.now() - started < 5_000) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
      const complete = buffer.split('\n\n').slice(0, -1); // the last piece may be partial
      data = complete.find((event) => event.startsWith('data: '))?.slice('data: '.length);
    }
  } finally {
    controller.abort();
  }
  expect(data, 'first data event').toBeDefined();
  expect(Date.now() - started, 'first event should arrive at once').toBeLessThan(3_000);

  const prices = JSON.parse(data!);
  expect(Object.keys(prices)).toContain('AAPL');
  expect(prices.AAPL).toMatchObject({ ticker: 'AAPL', price: expect.any(Number), direction: expect.any(String) });
});
