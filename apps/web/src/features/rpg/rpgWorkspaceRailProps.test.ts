import { describe, expect, it } from 'vitest';
import { createRpgWorkspaceRailProps } from './rpgWorkspaceRailProps';

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
});
