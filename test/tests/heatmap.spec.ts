import { expect, test, type Page } from '@playwright/test';
import { apiTrade, closePosition, dataPoints, getPortfolio, openApp, parseNumber, positionRows } from './support/app';

// Quantities chosen so the market values are far apart (~$130, ~$500, ~$1,100) and the
// tile areas have an unambiguous order.
const BUYS: Record<string, number> = { NVDA: 1, TSLA: 2, META: 2 };
const TICKERS = Object.keys(BUYS);

interface TileReading {
  ticker: string;
  sign: string | null;
  rgb: [number, number, number] | null;
  area: number;
  pnl: string | null;
  pnlPercent: string | null;
}

/** Read every tile and the matching positions-table cells in one synchronous pass (no tick in between). */
function readTiles(page: Page): Promise<TileReading[]> {
  return page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 1;
    const ctx = canvas.getContext('2d')!;
    const toRgb = (css: string): [number, number, number] => {
      ctx.clearRect(0, 0, 1, 1);
      ctx.fillStyle = css;
      ctx.fillRect(0, 0, 1, 1);
      const [r, g, b] = ctx.getImageData(0, 0, 1, 1).data;
      return [r, g, b];
    };
    // The tile's own background, or the first painted descendant's.
    const background = (el: Element): [number, number, number] | null => {
      const queue: Element[] = [el];
      while (queue.length) {
        const node = queue.shift()!;
        const color = getComputedStyle(node).backgroundColor;
        if (color && color !== 'transparent' && !/^rgba\(.*,\s*0\)$/.test(color)) return toRgb(color);
        queue.push(...Array.from(node.children));
      }
      return null;
    };
    const text = (testid: string) =>
      document.querySelector<HTMLElement>(`[data-testid="${testid}"]`)?.innerText ?? null;

    return Array.from(document.querySelectorAll<HTMLElement>('[data-testid^="heatmap-tile-"]')).map((tile) => {
      const ticker = tile.dataset.testid!.slice('heatmap-tile-'.length);
      const box = tile.getBoundingClientRect();
      return {
        ticker,
        sign: tile.getAttribute('data-pnl-sign'),
        rgb: background(tile),
        area: box.width * box.height,
        pnl: text(`position-pnl-${ticker}`),
        pnlPercent: text(`position-pnl-percent-${ticker}`),
      };
    });
  });
}

test.beforeEach(async ({ request }) => {
  for (const ticker of TICKERS) {
    await closePosition(request, ticker);
    await apiTrade(request, ticker, 'buy', BUYS[ticker]);
  }
});

test.afterEach(async ({ request }) => {
  for (const ticker of TICKERS) await closePosition(request, ticker);
});

test('heatmap tiles match positions, are sized by weight and colored by P&L sign', async ({ page, request }) => {
  // Tiles fade background-color over 500 ms; a computed style read mid-fade mixes the old and
  // new colors. The app drops the transition under reduced motion, so colors read settled.
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openApp(page);
  await expect(page.getByTestId('heatmap')).toBeVisible();
  await expect(page.getByTestId('heatmap-empty')).toHaveCount(0);
  for (const ticker of TICKERS) await expect(page.getByTestId(`heatmap-tile-${ticker}`)).toBeVisible();
  for (const ticker of TICKERS) await expect(page.getByTestId(`position-pnl-${ticker}`)).toHaveText(/\d/);

  // One tile per position, no cash tile.
  const positionTickers = await positionRows(page).evaluateAll((rows) =>
    rows.map((r) => (r as HTMLElement).dataset.testid!.slice('position-row-'.length)).sort(),
  );
  const tiles = await readTiles(page);
  expect(tiles.map((t) => t.ticker).sort()).toEqual(positionTickers);

  // Larger market value -> larger tile.
  const portfolio = await getPortfolio(request);
  const value = (t: string) => portfolio.positions.find((p) => p.ticker === t)!.market_value ?? 0;
  const area = (t: string) => tiles.find((tile) => tile.ticker === t)!.area;
  const byValue = [...TICKERS].sort((a, b) => value(a) - value(b));
  for (let i = 1; i < byValue.length; i++) {
    expect(area(byValue[i]), `${byValue[i]} tile should be larger than ${byValue[i - 1]}`).toBeGreaterThan(
      area(byValue[i - 1]),
    );
  }

  // Prices move every 500 ms, so sample several times while P&L drifts around zero.
  let checkedSigns = 0;
  for (let sample = 0; sample < 6; sample++) {
    for (const tile of await readTiles(page)) {
      expect(['positive', 'negative', 'zero'], `${tile.ticker} data-pnl-sign`).toContain(tile.sign);
      expect(tile.rgb, `${tile.ticker} tile has a background color`).not.toBeNull();
      expect(tile.pnl, `${tile.ticker} has a P&L cell`).not.toBeNull();
      // The sign is taken from the dollar P&L rounded to cents, exactly as the table shows it.
      const pnl = parseNumber(tile.pnl!);
      const expected = pnl > 0 ? 'positive' : pnl < 0 ? 'negative' : 'zero';
      expect(tile.sign, `${tile.ticker} tile sign vs P&L ${tile.pnl}`).toBe(expected);
      if (expected === 'zero') continue;
      checkedSigns++;

      // Any non-zero P&L is tinted visibly (the neutral gray itself has green > red).
      const [r, g] = tile.rgb!;
      const where = `${tile.ticker} at ${tile.pnl} (${tile.pnlPercent}) is rgb(${tile.rgb!.join(', ')})`;
      if (expected === 'positive') expect(g, `${where}: should be green`).toBeGreaterThan(r);
      else expect(r, `${where}: should be red`).toBeGreaterThan(g);
    }

    // Colors are ordered with P&L: every gaining tile is at least as green as every losing tile.
    const tilesNow = await readTiles(page);
    const greenness = (t: TileReading) => t.rgb![1] - t.rgb![0];
    const gaining = tilesNow.filter((t) => t.sign === 'positive').map(greenness);
    const losing = tilesNow.filter((t) => t.sign === 'negative').map(greenness);
    if (gaining.length && losing.length) {
      expect(Math.min(...gaining), 'gaining tiles should be greener than losing tiles').toBeGreaterThanOrEqual(
        Math.max(...losing),
      );
    }
    await page.waitForTimeout(1_000);
  }
  expect(checkedSigns, 'at least some tiles should show a non-zero P&L').toBeGreaterThan(0);
});

test('P&L chart has history points', async ({ page }) => {
  await openApp(page);
  const chart = page.getByTestId('pnl-chart');
  await expect(chart).toBeVisible();
  // The seed snapshot plus one per trade made in beforeEach.
  await expect.poll(() => dataPoints(chart)).toBeGreaterThanOrEqual(2);
  await expect(chart.locator('canvas').first()).toBeVisible();
});
