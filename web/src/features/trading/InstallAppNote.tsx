import { useState } from 'react';
import type { TradingCommandAvailability } from './commands/tradingCommands';
import { useInstallApp } from './installedApp';

/** In the browser: why some keys are marked "app", and the install button when the browser offers one (TVP-4.5). */
export function InstallAppNote({ availability }: { availability: TradingCommandAvailability }) {
  const install = useInstallApp();
  const [outcome, setOutcome] = useState<string | null>(null);
  if (availability === 'installed') return null;
  return (
    <p className="trading-install-app-note">
      Keys marked “app” (Ctrl+T, Ctrl+W, Ctrl+Tab, Ctrl+1…9) belong to the browser; they work in the installed Omnix Trading app.
      {install ? (
        <button type="button" onClick={() => void install().then((accepted) => setOutcome(accepted ? 'Installed: open Omnix Trading from your apps.' : 'Not installed.'))}>
          Install app
        </button>
      ) : outcome ? null : <span> Install it from the browser’s menu (Install Omnix Trading).</span>}
      {outcome ? <span role="status"> {outcome}</span> : null}
    </p>
  );
}
