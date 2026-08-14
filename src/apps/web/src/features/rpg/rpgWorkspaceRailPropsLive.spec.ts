import { expect, test } from 'vitest';
import { createRpgWorkspaceRailProps } from './rpgWorkspaceRailProps';

test('maps live-shaped inputs into rail props', () => {
  const props = createRpgWorkspaceRailProps({
    enabled: true,
    suggestions: [{ id: 'one', label: 'Use', command: 'look around' }],
    modePayload: { ok: true, mode: 'rpg', role: 'suggest', owner: 'rpg_sim' },
    readoutPayload: {
      ok: true,
      turn: { category: 'general' },
      systems: ['journal'],
      effect_count: 1,
      grounding_status: 'checked',
    },
  });

  expect(props.hermesSuggestionState).toBe('ready');
  expect(props.hermesSuggestions[0]?.command).toBe('look around');
  expect(props.hermesRouteDecisionState).toBe('ready');
  expect(props.hermesTurnReadoutState).toBe('ready');
});
