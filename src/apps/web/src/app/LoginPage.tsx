import { Alert, Button, Center, Paper, PasswordInput, Stack, Text, Title } from '@mantine/core';
import { useEffect, useState, type FormEvent } from 'react';
import {
  AuthRequestError,
  fetchAuthSession,
  loginWithInstallCredential,
  oidcLoginUrl,
  type AuthSession,
} from '../api/authClient';

const ERROR_MESSAGES: Record<string, string> = {
  login_link_expired: 'That sign-in link has expired or was already used. Open Omnix from the launcher again, or sign in below.',
  sign_in_failed: 'Sign-in did not complete. Try again.',
  invalid_credential: 'That install credential is not valid.',
};

// Only same-origin absolute paths; mirrors the gateway's redirect rule.
export function safeNextPath(value: string | null): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.includes('\\')) return '/';
  return value;
}

function goTo(path: string): void {
  window.location.assign(path);
}

export function LoginPage() {
  const params = new URLSearchParams(window.location.search);
  const next = safeNextPath(params.get('next'));
  const [session, setSession] = useState<AuthSession | null>(null);
  const [credential, setCredential] = useState('');
  const [error, setError] = useState<string | null>(ERROR_MESSAGES[params.get('error') ?? ''] ?? null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void fetchAuthSession()
      .then((payload) => {
        if (cancelled) return;
        if (payload.authenticated || !payload.enforced) {
          goTo(next);
          return;
        }
        setSession(payload);
      })
      .catch(() => {
        if (!cancelled) setError('Omnix is not reachable. Check that the gateway is running.');
      });
    return () => {
      cancelled = true;
    };
  }, [next]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await loginWithInstallCredential(credential.trim());
      goTo(next);
    } catch (caught) {
      setError(
        caught instanceof AuthRequestError
          ? ERROR_MESSAGES.invalid_credential
          : 'Omnix is not reachable. Check that the gateway is running.',
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Center mih="100vh" p="md">
      <Paper withBorder p="xl" radius="md" maw={420} w="100%">
        <Stack gap="md">
          <Title order={2}>Sign in to Omnix</Title>
          {error ? (
            <Alert color="red" role="alert">
              {error}
            </Alert>
          ) : null}
          {session?.mode === 'oidc' ? (
            <Button component="a" href={oidcLoginUrl(next)}>
              Sign in with your organization
            </Button>
          ) : null}
          {session?.mode === 'local' ? (
            <form onSubmit={submit}>
              <Stack gap="sm">
                <Text size="sm" c="dimmed">
                  The launcher signs you in automatically. To sign in by hand, paste the install credential
                  shown by <code>python -m app.security show-install-credential</code>.
                </Text>
                <PasswordInput
                  label="Install credential"
                  value={credential}
                  onChange={(event) => setCredential(event.currentTarget.value)}
                  autoComplete="current-password"
                  required
                />
                <Button type="submit" loading={submitting} disabled={!credential.trim()}>
                  Sign in
                </Button>
              </Stack>
            </form>
          ) : null}
        </Stack>
      </Paper>
    </Center>
  );
}
