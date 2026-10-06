import { MantineProvider } from '@mantine/core';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LoginPage, safeNextPath } from './LoginPage';

function renderLogin(search = '') {
  window.history.replaceState({}, '', `/login${search}`);
  return render(
    <MantineProvider>
      <LoginPage />
    </MantineProvider>,
  );
}

function mockLocationAssign() {
  const assign = vi.fn();
  vi.spyOn(window, 'location', 'get').mockReturnValue({ ...window.location, assign });
  return assign;
}

describe('LoginPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState({}, '', '/');
  });

  it('keeps post-login navigation on this origin', () => {
    expect(safeNextPath('/trading?x=1')).toBe('/trading?x=1');
    expect(safeNextPath('https://evil.example')).toBe('/');
    expect(safeNextPath('//evil.example')).toBe('/');
    expect(safeNextPath('/\\evil.example')).toBe('/');
    expect(safeNextPath(null)).toBe('/');
  });

  it('signs in with the install credential and returns to the requested page', async () => {
    const fetchMock = vi.spyOn(window, 'fetch').mockImplementation(async (input) => {
      const url = String(input);
      if (url === '/api/auth/session') return Response.json({ enforced: true, mode: 'local', authenticated: false });
      if (url === '/api/auth/local/login') return Response.json({ enforced: true, mode: 'local', authenticated: true });
      throw new Error(`unexpected ${url}`);
    });
    renderLogin('?next=%2Ftrading');
    const assign = mockLocationAssign();
    const input = await screen.findByLabelText(/install credential/i);
    fireEvent.change(input, { target: { value: ' secret ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith('/trading'));
    const loginCall = fetchMock.mock.calls.find(([url]) => url === '/api/auth/local/login');
    expect(JSON.parse(String(loginCall?.[1]?.body))).toEqual({ credential: 'secret' });
  });

  it('reports a rejected credential', async () => {
    vi.spyOn(window, 'fetch').mockImplementation(async (input) => {
      if (String(input) === '/api/auth/session') return Response.json({ enforced: true, mode: 'local', authenticated: false });
      return new Response('{"detail":"invalid_credential"}', { status: 401 });
    });
    renderLogin();
    fireEvent.change(await screen.findByLabelText(/install credential/i), { target: { value: 'wrong' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('not valid');
  });

  it('offers single sign-on in OIDC mode', async () => {
    vi.spyOn(window, 'fetch').mockResolvedValue(Response.json({ enforced: true, mode: 'oidc', authenticated: false }));
    renderLogin('?next=%2Fchatbot');
    const link = await screen.findByRole('link', { name: /organization/i });
    expect(link).toHaveAttribute('href', '/api/auth/oidc/login?next=%2Fchatbot');
  });

  it('explains an expired launcher link', async () => {
    vi.spyOn(window, 'fetch').mockResolvedValue(Response.json({ enforced: true, mode: 'local', authenticated: false }));
    renderLogin('?error=login_link_expired');
    expect(await screen.findByRole('alert')).toHaveTextContent('expired');
  });
});
