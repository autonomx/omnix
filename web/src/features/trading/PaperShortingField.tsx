import { useState } from 'react';
import type { PaperAccount, PaperAccountSnapshot } from './paperTypes';
import { tradingPaperApi } from './tradingPaperApi';

/**
 * Shorting for a paper account (TVP-7.2a). When creating an account it is part of the form and starts on, as
 * TradingView's paper accounts do. In an account's settings it is saved at once, at the account's revision. Turning
 * it off stops new shorts; open shorts stay.
 */
export function PaperShortingField({
  mode, draftValue, onDraftChange, account, onSaved,
}: {
  mode: 'create' | 'settings';
  draftValue: boolean;
  onDraftChange: (value: boolean) => void;
  account: PaperAccount | null;
  onSaved: (snapshot: PaperAccountSnapshot) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const checked = mode === 'create' ? draftValue : Boolean(account?.allow_short);
  const change = (next: boolean) => {
    if (mode === 'create') {
      onDraftChange(next);
      return;
    }
    if (!account) return;
    setSaving(true);
    setError(null);
    void tradingPaperApi.updateAccountSettings(account, { allow_short: next })
      .then(onSaved)
      .catch((caught: unknown) => setError(caught instanceof Error && caught.message.includes('(409)')
        ? 'The account changed elsewhere; reopen its settings and try again.'
        : 'Shorting could not be changed.'))
      .finally(() => setSaving(false));
  };
  return (
    <fieldset>
      <legend>Shorting</legend>
      <label className="trading-account-check">
        <input type="checkbox" checked={checked} disabled={saving || (mode === 'settings' && !account)} onChange={(event) => change(event.target.checked)} />
        <span>Allow short positions</span>
      </label>
      <small className="trading-account-hint">A sell with no position opens a short, sized by the account&apos;s risk rule with a stop above the entry.</small>
      {error ? <small className="trading-account-hint" role="alert">{error}</small> : null}
    </fieldset>
  );
}
