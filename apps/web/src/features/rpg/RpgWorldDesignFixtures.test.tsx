import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  RPG_WORLD_DESIGN_BREAKPOINTS,
  RPG_WORLD_DESIGN_CHECKLIST,
  RpgWorldDesignFixtureCanvas,
  type RpgWorldDesignFixtureView,
} from './RpgWorldDesignFixtures';

function renderFixture(view: RpgWorldDesignFixtureView) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <RpgWorldDesignFixtureCanvas view={view} />
    </QueryClientProvider>,
  );
}

describe('RPG world-authoring deterministic design fixtures', () => {
  it('maps every approved page family and responsive baseline', () => {
    expect(RPG_WORLD_DESIGN_CHECKLIST.map((item) => item.fixture)).toEqual([
      'overview',
      'generation',
      'realm',
      'history',
      'collection',
      'entity',
    ]);
    expect(RPG_WORLD_DESIGN_CHECKLIST.every((item) => item.requirements.length >= 4)).toBe(true);
    expect(RPG_WORLD_DESIGN_BREAKPOINTS).toEqual([1440, 1024, 768, 390]);
  });

  it.each([
    ['overview', 'Aurelia, the Shattered Crown'],
    ['generation', 'World Generation'],
    ['realm', 'Realm Overview'],
    ['history', 'History of Aurelia'],
    ['collection', 'World Collection'],
    ['entity', 'Mira Vale'],
  ] as const)('renders the %s visual fixture without provider or network data', (view, heading) => {
    renderFixture(view);
    expect(screen.getAllByRole('heading', { name: heading }).length).toBeGreaterThan(0);
  });
});
