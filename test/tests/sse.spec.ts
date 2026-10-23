import net from 'node:net';
import { expect, test } from '@playwright/test';
import { dataPoints, expectPricesToMove, openApp } from './support/app';

/**
 * A TCP relay to the app that can cut every open connection.
 *
 * Chromium's offline emulation (context.setOffline) only fails *new* requests; an EventSource
 * that is already streaming keeps receiving events. So the test loads the app through this
 * relay, cuts the live stream here and uses setOffline to keep reconnect attempts failing
 * until the "network" comes back. The server itself is never touched.
 */
async function startRelay(target: URL) {
  const sockets = new Set<net.Socket>();
  const server = net.createServer((client) => {
    const upstream = net.connect(Number(target.port || 80), target.hostname);
    for (const socket of [client, upstream]) {
      sockets.add(socket);
      socket.on('error', () => {});
      socket.on('close', () => {
        client.destroy();
        upstream.destroy();
        sockets.delete(socket);
      });
    }
    client.pipe(upstream);
    upstream.pipe(client);
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  return {
    url: `http://127.0.0.1:${(server.address() as net.AddressInfo).port}`,
    dropConnections: () => sockets.forEach((socket) => socket.destroy()),
    close: () => {
      sockets.forEach((socket) => socket.destroy());
      return new Promise<void>((resolve) => server.close(() => resolve()));
    },
  };
}

test('price stream reconnects after the network drops', async ({ browser, baseURL }) => {
  const relay = await startRelay(new URL(baseURL!));
  const context = await browser.newContext({ baseURL: relay.url });
  try {
    const page = await context.newPage();
    await openApp(page);
    const status = page.getByTestId('connection-status');
    const sparkline = page.getByTestId('sparkline-AAPL');
    await expectPricesToMove(page);

    await context.setOffline(true);
    relay.dropConnections();
    await expect(status).toHaveAttribute('data-status', /^(reconnecting|disconnected)$/, { timeout: 15_000 });
    const pointsWhileOffline = await dataPoints(sparkline);

    await context.setOffline(false);
    await expect(status).toHaveAttribute('data-status', 'connected', { timeout: 20_000 });
    await expect.poll(() => dataPoints(sparkline)).toBeGreaterThan(pointsWhileOffline);
    await expectPricesToMove(page);
  } finally {
    await context.close();
    await relay.close();
  }
});
