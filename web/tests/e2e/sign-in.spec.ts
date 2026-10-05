import { expect, test, type Page, type Route } from '@playwright/test';

// WP-4.1: the web app end to end with local sign-in, through the launcher's
// one-time link or the install credential. The login fixture plays the
// gateway's /api/auth contract (cookies, CSRF, single-use codes); the gateway
// side of the same flow runs against PostgreSQL in
// src/tests/persistence/test_auth_sessions_integration.py.

const CREDENTIAL = 'install-credential-for-e2e';

class LocalAuthGateway {
  readonly sessions = new Map<string, string>(); // session token -> csrf token
  readonly codes = new Set<string>();
  readonly unsafeRequests: Array<{ path: string; csrf: string | null; session: string | null }> = [];
  private counter = 0;

  issueLoginCode(): string {
    const code = `code-${++this.counter}`;
    this.codes.add(code);
    return code;
  }

  async install(page: Page): Promise<void> {
    await page.route((url) => url.pathname === '/events' || url.pathname.startsWith('/events/'), (route) => route.abort());
    await page.route((url) => url.pathname.startsWith('/api/'), (route) => this.handle(route));
  }

  private session(route: Route): string | null {
    const cookies = route.request().headers()['cookie'] ?? '';
    const token = cookies.split(';').map((part) => part.trim()).find((part) => part.startsWith('omnix_session='))?.slice('omnix_session='.length);
    return token && this.sessions.has(token) ? token : null;
  }

  private issue(): { token: string; cookies: string[] } {
    const token = `session-${++this.counter}`;
    const csrf = `csrf-${this.counter}`;
    this.sessions.set(token, csrf);
    return {
      token,
      cookies: [
        `omnix_session=${token}; Path=/; HttpOnly; SameSite=Strict`,
        `omnix_csrf=${csrf}; Path=/; SameSite=Strict`,
      ],
    };
  }

  private static json(route: Route, status: number, body: unknown, headers: Record<string, string> = {}): Promise<void> {
    return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body), headers });
  }

  private async handle(route: Route): Promise<void> {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const session = this.session(route);
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
      this.unsafeRequests.push({ path: url.pathname, csrf: request.headers()['x-omnix-csrf'] ?? null, session });
    }
    if (url.pathname === '/api/auth/session') {
      return LocalAuthGateway.json(route, 200, session
        ? { enforced: true, mode: 'local', authenticated: true, user_id: 'user:local', workspace_id: 'workspace:local', roles: ['owner'], auth_method: 'session:local' }
        : { enforced: true, mode: 'local', authenticated: false, roles: [] });
    }
    if (url.pathname === '/api/auth/local/login' && method === 'POST') {
      const body = request.postDataJSON() as { credential?: string };
      if (body.credential !== CREDENTIAL) return LocalAuthGateway.json(route, 401, { detail: 'invalid_credential' });
      const issued = this.issue();
      return route.fulfill({
        status: 200, contentType: 'application/json',
        headers: { 'set-cookie': issued.cookies.join('\n') },
        body: JSON.stringify({ enforced: true, mode: 'local', authenticated: true, user_id: 'user:local', workspace_id: 'workspace:local', roles: ['owner'], auth_method: 'session:local' }),
      });
    }
    if (url.pathname === '/api/auth/local/callback') {
      const code = url.searchParams.get('code') ?? '';
      if (!this.codes.delete(code)) return route.fulfill({ status: 303, headers: { location: '/login?error=login_link_expired' } });
      const issued = this.issue();
      const next = url.searchParams.get('next') ?? '/';
      return route.fulfill({ status: 303, headers: { location: next.startsWith('/') && !next.startsWith('//') ? next : '/', 'set-cookie': issued.cookies.join('\n') } });
    }
    if (url.pathname === '/api/auth/logout' && method === 'POST') {
      if (session && request.headers()['x-omnix-csrf'] !== this.sessions.get(session)) return LocalAuthGateway.json(route, 403, { detail: 'csrf_failed' });
      if (session) this.sessions.delete(session);
      return route.fulfill({
        status: 204,
        headers: { 'set-cookie': ['omnix_session=; Path=/; Max-Age=0', 'omnix_csrf=; Path=/; Max-Age=0'].join('\n') },
      });
    }
    if (url.pathname === '/api/auth/sessions') {
      if (!session) return LocalAuthGateway.json(route, 401, { detail: 'authentication_required' });
      return LocalAuthGateway.json(route, 200, { sessions: [...this.sessions.keys()].map((token, index) => ({
        id: String(index).padStart(16, '0'), auth_method: 'local', created_at: '2026-10-03T08:00:00Z',
        last_seen_at: '2026-10-03T09:00:00Z', expires_at: '2026-10-10T08:00:00Z', current: token === session,
      })) });
    }
    // Every other gateway call: deny without a session, as the gateway does.
    if (!session) return LocalAuthGateway.json(route, 401, { detail: 'authentication_required' }, { 'www-authenticate': 'Bearer realm="omnix"' });
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && request.headers()['x-omnix-csrf'] !== this.sessions.get(session)) {
      return LocalAuthGateway.json(route, 403, { detail: 'csrf_failed' });
    }
    return LocalAuthGateway.json(route, 503, { detail: 'not part of this test' });
  }
}

let gateway: LocalAuthGateway;

test.beforeEach(async ({ page }) => {
  gateway = new LocalAuthGateway();
  await gateway.install(page);
});

test('a signed-out browser is sent to sign in and comes back after the credential', async ({ page }) => {
  await page.goto('/settings');
  await expect(page).toHaveURL(/\/login\?next=%2Fsettings$/);

  await page.getByLabel(/install credential/i).fill('wrong');
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page.getByRole('alert')).toContainText('not valid');

  await page.getByLabel(/install credential/i).fill(CREDENTIAL);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(page.getByRole('button', { name: 'Sign out of Omnix' })).toBeVisible();
  // The session cookie is HttpOnly: the page never sees it.
  expect(await page.evaluate(() => document.cookie)).not.toContain('omnix_session');
  await page.getByRole('navigation', { name: 'Settings category list' }).getByRole('button', { name: 'Overview' }).click();
  await expect(page.getByRole('list', { name: 'Signed-in sessions' })).toContainText('This browser');
});

test('the launcher link signs in once and opens the requested workspace', async ({ page }) => {
  const code = gateway.issueLoginCode();
  await page.goto(`/api/auth/local/callback?code=${code}&next=%2Fjobs`);
  await expect(page).toHaveURL(/\/jobs$/);
  await expect(page.getByRole('button', { name: 'Sign out of Omnix' })).toBeVisible();

  await page.context().clearCookies();
  await page.goto(`/api/auth/local/callback?code=${code}&next=%2Fjobs`);
  await expect(page).toHaveURL(/\/login\?error=login_link_expired$/);
  await expect(page.getByRole('alert')).toContainText('expired');
});

test('sign-out sends the CSRF token and ends the session', async ({ page }) => {
  await page.goto(`/api/auth/local/callback?code=${gateway.issueLoginCode()}&next=%2Fsettings`);
  await expect(page.getByRole('button', { name: 'Sign out of Omnix' })).toBeVisible();

  await page.getByRole('button', { name: 'Sign out of Omnix' }).click();
  await expect(page).toHaveURL(/\/login/);
  const logout = gateway.unsafeRequests.find((entry) => entry.path === '/api/auth/logout');
  expect(logout?.csrf).toMatch(/^csrf-/);
  expect(gateway.sessions.size).toBe(0);
  // Another visit needs a new sign-in.
  await page.goto('/settings');
  await expect(page).toHaveURL(/\/login\?next=%2Fsettings$/);
});
