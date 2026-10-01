import { useEffect, useState } from 'react';
import { fetchAuthSession, logout } from '../api/authClient';
import { LOGIN_PATH } from './viewApiScope';

// Shown only when the gateway enforces sign-in and this browser has a session.
export function SignOutButton() {
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void fetchAuthSession()
      .then((session) => {
        if (!cancelled) setVisible(session.enforced && session.authenticated);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  if (!visible) return null;
  return (
    <button
      type="button"
      aria-label="Sign out of Omnix"
      disabled={busy}
      onClick={() => {
        setBusy(true);
        void logout()
          .catch(() => undefined)
          .finally(() => window.location.assign(LOGIN_PATH));
      }}
    >
      Sign out
    </button>
  );
}
