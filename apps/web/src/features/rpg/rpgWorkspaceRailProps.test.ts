import { describe, expect, it } from 'vitest';
import { createRpgWorkspaceRailProps, failedRpgWorkspaceRailPayload } from './rpgWorkspaceRailProps';

describe('createRpgWorkspaceRailProps', () => {
  it('combines live route suggestions and readout props', () => {
    const props = createRpgWorkspaceRailProps({
      enabled: true,
      suggestions: [{ id: 'one', label: 'Ask', command: 'ask at the tavern' }],
      modePayload: { ok: true, mode: 'rpg', role: 'suggest', owner: 'rpg_sim', review_required: false, boundary: 'Ready.' },
      readoutPayload: {
        ok: true,
        turn: { category: 'dialogue' },
        systems: ['command_parser'],
        effect_count: 1,
        grounding_status: 'checked',
      },
    });

    expect(props.hermesSuggestionState).toBe('ready');
    expect(props.hermesSuggestions).toHaveLength(1);
    expect(props.hermesRouteDecision?.mode).toBe('rpg');
    expect(props.hermesRouteDecisionState).toBe('ready');
    expect(props.hermesTurnReadout?.category).toBe('dialogue');
    expect(props.hermesTurnReadoutState).toBe('ready');
  });

  it('keeps disabled sessions idle', () => {
    const props = createRpgWorkspaceRailProps({ enabled: false });

    expect(props.hermesSuggestionState).toBe('idle');
    expect(props.hermesTurnReadoutState).toBe('idle');
  });

  it('maps pending query flags into loading rail states', () => {
    const props = createRpgWorkspaceRailProps({
      enabled: true,
      suggestionsPending: true,
      modePending: true,
      readoutPending: true,
    });

    expect(props.hermesSuggestionState).toBe('loading');
    expect(props.hermesRouteDecisionState).toBe('loading');
    expect(props.hermesTurnReadoutState).toBe('loading');
  });

  it('maps failed query flags into error rail states', () => {
    const props = createRpgWorkspaceRailProps({
      enabled: true,
      suggestionsFailed: true,
      modeFailed: true,
      readoutFailed: true,
    });

    expect(props.hermesSuggestionState).toBe('error');
    expect(props.hermesRouteDecisionState).toBe('error');
    expect(props.hermesTurnReadoutState).toBe('error');
  });

  it('normalizes query failure flags for workspace callers', () => {
    expect(failedRpgWorkspaceRailPayload({ ok: true }, { isError: false })).toBe(false);
    expect(failedRpgWorkspaceRailPayload({ ok: false }, { isError: false })).toBe(true);
    expect(failedRpgWorkspaceRailPayload({ ok: true }, { isError: true })).toBe(true);
  });
});
