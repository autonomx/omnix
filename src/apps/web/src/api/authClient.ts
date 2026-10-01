import type { components } from './generated/types';

export type AuthSession = components['schemas']['AuthSessionResponse'];
export type LocalLoginBody = components['schemas']['LocalLoginRequest'];

export class AuthRequestError extends Error {
  constructor(readonly status: number) {
    super(`auth_request_failed:${status}`);
  }
}

export async function fetchAuthSession(): Promise<AuthSession> {
  const response = await fetch('/api/auth/session', { credentials: 'same-origin' });
  if (!response.ok) throw new AuthRequestError(response.status);
  return (await response.json()) as AuthSession;
}

export async function loginWithInstallCredential(credential: string): Promise<AuthSession> {
  const body: LocalLoginBody = { credential };
  const response = await fetch('/api/auth/local/login', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new AuthRequestError(response.status);
  return (await response.json()) as AuthSession;
}

export async function logout(): Promise<void> {
  // The view firewall adds X-Omnix-Client and the CSRF header.
  const response = await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' });
  if (!response.ok && response.status !== 404) throw new AuthRequestError(response.status);
}

export function oidcLoginUrl(next: string): string {
  return `/api/auth/oidc/login?next=${encodeURIComponent(next)}`;
}
