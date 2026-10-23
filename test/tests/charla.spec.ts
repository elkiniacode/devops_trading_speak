import { expect, test, type APIRequestContext, type Browser, type BrowserContext, type Locator, type Page } from '@playwright/test';

// Live-talk ("charla") sections: planning/charla/CONTRACT.md §5, §6, §9 and §10.
//
// The local runner (scripts/start-server.mjs) starts the app with CHARLA_ADMIN_KEY=e2e, CHARLA_DEV_LINKS=true
// (register returns dev_link_token), CHARLA_PHONE_AT=off and no Resend key. charla_only stays false, so the
// FinAlly specs run against the same server. Charla tables are separate from the portfolio, and each test here
// starts with POST /api/charla/admin/reset, so nothing depends on file or test order.

const ADMIN_KEY = process.env.CHARLA_E2E_KEY ?? 'e2e';
const ADMIN = { 'X-Admin-Key': ADMIN_KEY };

// content.py QUESTIONS[0]: the question text and its correct option (index 2).
const Q1_TEXT = '¿Qué diferencia a un agente de un chatbot?';
const Q1_CORRECT = /Decide pasos y usa herramientas/;

const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } as const;
const STAGE = { width: 1440, height: 810 } as const;

const SALA_URL = /\/charla\/sala\/$/;

// ---------------------------------------------------------------------------------------------
// API helpers

interface AttendeeView {
  state: { step: number; kind: string; phase: 'idle' | 'open' | 'closed' | 'revealed'; question: { text: string } | null };
  me: {
    username: string;
    verified: boolean;
    score: number;
    rank: number | null;
    answer: { step: number; choice: number | null } | null;
    result: { correct: boolean | null; points: number } | null;
  } | null;
}

async function resetCharla(request: APIRequestContext): Promise<void> {
  const res = await request.post('/api/charla/admin/reset', { headers: ADMIN, data: { confirm: 'RESET' } });
  expect(res.status(), `admin reset: ${await res.text()}`).toBe(200);
}

async function me(request: APIRequestContext, token: string): Promise<AttendeeView> {
  const res = await request.get('/api/charla/me', { headers: { Authorization: `Bearer ${token}` } });
  expect(res.status(), `GET /api/charla/me: ${await res.text()}`).toBe(200);
  return (await res.json()) as AttendeeView;
}

/** A username that is unique per run and valid (2–24 chars: letters, digits, space). */
function uniqueName(prefix: string): string {
  return `${prefix} ${Date.now().toString(36).slice(-6)}`;
}

function uniqueEmail(tag: string): string {
  return `${tag}.${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}@example.invalid`;
}

// ---------------------------------------------------------------------------------------------
// Page helpers. data-testids were requested from the component owners; role/text fallbacks keep the spec
// working if one is missing.

function baseURL(): string {
  const url = test.info().project.use.baseURL;
  if (!url) throw new Error('baseURL is not configured');
  return url;
}

async function newPhone(browser: Browser): Promise<BrowserContext> {
  return browser.newContext({ ...PHONE, baseURL: baseURL() });
}

const registro = (page: Page) => ({
  username: page.getByTestId('charla-username').or(page.getByLabel(/usuario|nombre/i)).first(),
  email: page.getByTestId('charla-email').or(page.locator('input[type="email"]')).first(),
  submit: page.getByTestId('charla-submit').or(page.getByRole('button', { name: /ENTRAR/i })).first(),
  waiting: page.getByTestId('charla-waiting').or(page.getByText(/revisa tu correo/i)).first(),
});

const presenter = (page: Page) => ({
  launch: page.getByTestId('pres-launch').or(page.getByRole('button', { name: /LANZAR/i })).first(),
  close: page.getByTestId('pres-close').or(page.getByRole('button', { name: /CERRAR/i })).first(),
  reveal: page.getByTestId('pres-reveal').or(page.getByRole('button', { name: /REVELAR/i })).first(),
  rankingTab: page
    .getByTestId('pres-tab-ranking')
    .or(page.getByRole('tab', { name: /RANKING/i }))
    .or(page.getByRole('button', { name: /RANKING/i }))
    .first(),
});

/** Click a presenter control until the room reaches `phase` (the UI may ignore clicks until its stream catches up). */
async function presenterStep(
  request: APIRequestContext,
  token: string,
  button: Locator,
  phase: AttendeeView['state']['phase'],
): Promise<void> {
  const current = async () => (await me(request, token)).state.phase;
  await expect(async () => {
    if ((await current()) !== phase) await button.click({ timeout: 3_000 });
    await expect.poll(current, { timeout: 3_000 }).toBe(phase);
  }).toPass({ timeout: 20_000 });
}

async function sessionToken(page: Page): Promise<string> {
  const token = await page.evaluate(() => localStorage.getItem('charla.token'));
  expect(token, 'the Sala should keep the session token in localStorage (charla.token)').toBeTruthy();
  return token!;
}

// ---------------------------------------------------------------------------------------------

test('GET /charla redirects to /charla/', async ({ request }) => {
  const res = await request.get('/charla', { maxRedirects: 0 });
  expect([301, 302, 307, 308]).toContain(res.status());
  expect(res.headers()['location']).toMatch(/\/charla\/$/);

  const page = await request.get('/charla/');
  expect(page.status()).toBe(200);
  expect(page.headers()['content-type']).toContain('text/html');
});

test('API: a pending registration is approved once its link is opened', async ({ request }) => {
  await resetCharla(request);
  const username = uniqueName('Api QA');
  const email = uniqueEmail('api');

  const check = await (await request.get('/api/charla/username', { params: { u: username } })).json();
  expect(check).toMatchObject({ valid: true, available: true, message: null });

  const reg = await request.post('/api/charla/register', { data: { username, email } });
  expect(reg.status(), await reg.text()).toBe(200);
  const body = await reg.json();
  expect(body).toMatchObject({ status: 'link_sent', email, username });
  expect(body.pending).toBeTruthy();
  expect(body.dev_link_token, 'CHARLA_DEV_LINKS=true must return dev_link_token').toBeTruthy();

  const waiting = await request.get('/api/charla/register/status', { params: { p: body.pending } });
  expect(await waiting.json()).toEqual({ status: 'waiting' });

  const verified = await request.post('/api/charla/verify', { data: { v: body.dev_link_token } });
  expect(verified.status(), await verified.text()).toBe(200);
  expect(await verified.json()).toMatchObject({ username });

  const approved = await (await request.get('/api/charla/register/status', { params: { p: body.pending } })).json();
  expect(approved).toMatchObject({ status: 'in', username });
  const view = await me(request, approved.token);
  expect(view.me).toMatchObject({ username, verified: true });

  // The name is now held by an active attendee.
  const taken = await (await request.get('/api/charla/username', { params: { u: username } })).json();
  expect(taken).toMatchObject({ valid: true, available: false });
  expect(taken.message).toContain('Ese nombre ya está en uso');

  const bad = await request.post('/api/charla/admin/launch', { headers: { 'X-Admin-Key': 'wrong' } });
  expect(bad.status()).toBe(401);
});

test('attendee registers, enters by link, answers, sees the result and ranks', async ({ browser, page, request }) => {
  test.setTimeout(150_000);
  await resetCharla(request);
  const username = uniqueName('Ana QA');
  const email = uniqueEmail('ana');

  const phoneCtx = await newPhone(browser);
  const linkCtx = await newPhone(browser);
  const otherCtx = await newPhone(browser);
  try {
    const phone = await phoneCtx.newPage();
    let registerCalls = 0;
    phone.on('request', (r) => {
      if (r.method() === 'POST' && r.url().includes('/api/charla/register')) registerCalls += 1;
    });

    // --- Registration: username + email, then the waiting step.
    await test.step('register and wait for the link', async () => {
      await phone.goto('/charla/');
      const form = registro(phone);
      await form.username.fill(username);
      await form.email.fill(email);
      const response = phone.waitForResponse(
        (r) => r.url().includes('/api/charla/register') && !r.url().includes('/status') && r.request().method() === 'POST',
      );
      await form.submit.click();
      const res = await response;
      expect(res.status(), await res.text()).toBe(200);
      const body = await res.json();
      expect(body.status).toBe('link_sent');
      expect(body.dev_link_token).toBeTruthy();
      await expect(form.waiting).toBeVisible();

      // --- The email link opens in another browser; the ORIGINAL tab must get in on its own.
      const linkPage = await linkCtx.newPage();
      const verify = linkPage.waitForResponse(
        (r) => r.url().includes('/api/charla/verify') && r.request().method() === 'POST',
      );
      await linkPage.goto(`/charla/entrar/#v=${body.dev_link_token}`);
      expect((await verify).status()).toBe(200);
      await expect(phone).toHaveURL(SALA_URL, { timeout: 20_000 });
    });

    const token = await sessionToken(phone);
    expect((await me(request, token)).me).toMatchObject({ username, verified: true });

    // --- Someone else tries the same name with another email.
    await test.step('a taken username is refused', async () => {
      const other = await otherCtx.newPage();
      await other.goto('/charla/');
      const form = registro(other);
      await form.username.fill(username);
      await form.email.fill(uniqueEmail('otra'));
      if (await form.submit.isEnabled()) await form.submit.click();
      await expect(other.getByText(/Ese nombre ya está en uso/).first()).toBeVisible();
      await expect(other).not.toHaveURL(SALA_URL);
    });

    // --- Presenter on a 1440x810 stage.
    await page.setViewportSize(STAGE);
    page.on('dialog', (dialog) => dialog.accept());
    await page.goto(`/charla/presentador/#key=${ADMIN_KEY}`);
    const pres = presenter(page);
    await expect(pres.launch).toBeVisible();

    await test.step('presenter launches Q1 and the attendee answers', async () => {
      await presenterStep(request, token, pres.launch, 'open');
      await expect(phone.getByText(Q1_TEXT).first()).toBeVisible();

      const answer = phone.waitForResponse(
        (r) => r.url().includes('/api/charla/answer') && r.request().method() === 'POST',
      );
      await phone.getByRole('button', { name: Q1_CORRECT }).click();
      const res = await answer;
      expect(res.status(), await res.text()).toBe(200);
      expect(await res.json()).toEqual({ accepted: true });
      await expect(phone.getByText(/Respuesta registrada/i).first()).toBeVisible();
    });

    await test.step('presenter closes and reveals; the attendee sees CORRECTO with points', async () => {
      await presenterStep(request, token, pres.close, 'closed');
      await presenterStep(request, token, pres.reveal, 'revealed');

      const view = await me(request, token);
      expect(view.me?.result?.correct).toBe(true);
      const points = view.me!.result!.points;
      expect(points).toBeGreaterThanOrEqual(500);
      expect(points).toBeLessThanOrEqual(1000);

      await expect(phone.getByText(/(^|[^A-Z])CORRECTO/).first()).toBeVisible();
      await expect(phone.getByText(/NO ERA ESA/)).toHaveCount(0);
      const shown = await phone.evaluate((n) => n.toLocaleString('es-CO'), points);
      await expect(phone.locator('body')).toContainText(shown);
    });

    await test.step('the RANKING tab lists the attendee', async () => {
      await pres.rankingTab.click();
      const list = page.getByTestId('pres-ranking');
      const scope = (await list.count()) > 0 ? list : page.locator('body');
      await expect(scope.getByText(username).first()).toBeVisible();
    });

    await test.step('a reload returns to the Sala without registering again', async () => {
      const before = registerCalls;
      await phone.reload();
      await expect(phone).toHaveURL(SALA_URL);
      await expect(phone.getByText(/(^|[^A-Z])CORRECTO/).first()).toBeVisible();
      expect(registerCalls).toBe(before);
      expect(await sessionToken(phone)).toBe(token);
    });
  } finally {
    await Promise.all([phoneCtx.close(), linkCtx.close(), otherCtx.close()]);
  }
});
