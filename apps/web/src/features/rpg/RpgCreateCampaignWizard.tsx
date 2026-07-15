import { useEffect, useRef, useState } from 'react';
import type { RpgLaunchResponse, RpgNewGameRequest } from '../../api/client';
import { loadSettingsProfile } from '../settings/settingsApi';
import { RpgCreateCampaignWizard as LegacyRpgCreateCampaignWizard } from './RpgCreateCampaignWizardLegacy';
import { applyRpgWizardDefaults, rpgWizardDefaultsFromSettings } from './rpgWizardDefaults';

interface RpgCreateCampaignWizardProps {
  onCreateCampaign?: (request: RpgNewGameRequest) => Promise<RpgLaunchResponse>;
  onEnterWorld?: () => void;
}

type WorldForgeDepth = 'quick' | 'standard' | 'epic';

const depthOptions: Array<{
  value: WorldForgeDepth;
  label: string;
  detail: string;
}> = [
  {
    value: 'quick',
    label: 'Quick',
    detail: '12–20 lore pages, 4–6 major NPCs, 5–8 locations, 3–4 factions.',
  },
  {
    value: 'standard',
    label: 'Standard',
    detail: '30–50 lore pages, 8–12 major NPCs, 10–16 locations, 5–8 factions.',
  },
  {
    value: 'epic',
    label: 'Epic',
    detail: '70–120 lore pages, 15–25 major NPCs, 20–35 locations, 8–14 factions.',
  },
];

export function RpgCreateCampaignWizard(props: RpgCreateCampaignWizardProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const touchedRef = useRef(false);
  const applyingRef = useRef(false);
  const [worldForgeDepth, setWorldForgeDepth] = useState<WorldForgeDepth>('standard');

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

  const createCampaign = props.onCreateCampaign
    ? async (request: RpgNewGameRequest): Promise<RpgLaunchResponse> => {
        const enriched = {
          ...request,
          world_forge: {
            enabled: true,
            depth: worldForgeDepth,
            background_expansion: false,
            use_hermes: true,
            require_consistency_audit: true,
            require_opening_dossiers: true,
          },
        } as RpgNewGameRequest;
        return props.onCreateCampaign?.(enriched) as Promise<RpgLaunchResponse>;
      }
    : undefined;

  return (
    <div ref={rootRef} style={{ display: 'contents' }} onChangeCapture={markTouched} onInputCapture={markTouched}>
      <section
        aria-label="World generation depth"
        style={{
          border: '1px solid var(--border-subtle, rgba(255,255,255,.12))',
          borderRadius: 14,
          padding: 14,
          marginBottom: 14,
          background: 'var(--surface-elevated, rgba(255,255,255,.035))',
        }}
      >
        <div style={{ fontWeight: 700, marginBottom: 4 }}>World Forge depth</div>
        <div style={{ opacity: 0.72, fontSize: 13, marginBottom: 10 }}>
          Omnix creates a linked Campaign Bible, rich opening dossiers, a consistency audit, and a retrieval index before the first turn.
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 8 }}>
          {depthOptions.map((option) => {
            const selected = worldForgeDepth === option.value;
            return (
              <button
                key={option.value}
                type="button"
                aria-pressed={selected}
                onClick={() => setWorldForgeDepth(option.value)}
                style={{
                  textAlign: 'left',
                  borderRadius: 10,
                  border: selected
                    ? '1px solid var(--accent, #8ea7ff)'
                    : '1px solid var(--border-subtle, rgba(255,255,255,.12))',
                  background: selected
                    ? 'color-mix(in srgb, var(--accent, #8ea7ff) 16%, transparent)'
                    : 'transparent',
                  padding: 10,
                  color: 'inherit',
                  cursor: 'pointer',
                }}
              >
                <strong style={{ display: 'block' }}>{option.label}</strong>
                <span style={{ display: 'block', opacity: 0.7, fontSize: 12, marginTop: 4 }}>{option.detail}</span>
              </button>
            );
          })}
        </div>
      </section>
      <LegacyRpgCreateCampaignWizard {...props} onCreateCampaign={createCampaign} />
    </div>
  );
}
