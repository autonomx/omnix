import { useEffect, useRef } from 'react';
import type { RpgLaunchResponse, RpgNewGameRequest } from '../../api/client';
import { loadSettingsProfile } from '../settings/settingsApi';
import { RpgCreateCampaignWizard as LegacyRpgCreateCampaignWizard } from './RpgCreateCampaignWizardLegacy';
import { applyRpgWizardDefaults, rpgWizardDefaultsFromSettings } from './rpgWizardDefaults';

interface RpgCreateCampaignWizardProps {
  onCreateCampaign?: (request: RpgNewGameRequest) => Promise<RpgLaunchResponse>;
  onEnterWorld?: () => void;
}

export function RpgCreateCampaignWizard(props: RpgCreateCampaignWizardProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const touchedRef = useRef(false);
  const applyingRef = useRef(false);

  useEffect(() => {
    let active = true;
    loadSettingsProfile()
      .then(({ profile }) => {
        if (!active || touchedRef.current || !rootRef.current) return;
        applyingRef.current = true;
        try {
          applyRpgWizardDefaults(rootRef.current, rpgWizardDefaultsFromSettings(profile));
        } finally {
          applyingRef.current = false;
        }
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  const markTouched = () => {
    if (!applyingRef.current) touchedRef.current = true;
  };

  return (
    <div ref={rootRef} style={{ display: 'contents' }} onChangeCapture={markTouched} onInputCapture={markTouched}>
      <LegacyRpgCreateCampaignWizard {...props} />
    </div>
  );
}
