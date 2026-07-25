import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { RpgAuthoringSection } from '../../api/rpgWorldAuthoringClient';
import type { RpgWorldGenerationRun } from '../../api/rpgWorldLibraryClient';
import { RpgWorldGenerationDashboard } from './RpgWorldGenerationDashboard';

const section: RpgAuthoringSection = {
  id: 'regions',
  label: 'Regions',
  group: 'world',
  page_kind: 'collection',
  topic_ids: ['regions'],
  entity_kind: 'region',
  dependencies: [],
  required_before_launch: true,
  supports_generation: true,
  supports_images: true,
  supports_entity_editing: true,
  operational_status: 'complete',
  editorial_status: 'unreviewed',
  entity_count: 4,
};

const previousRun: RpgWorldGenerationRun = {
  run_id: 'run:previous',
  world_id: 'world:aurelia',
  draft_revision: 2,
  status: 'review',
  graph: {},
  context: {},
  settings: { provider_route: 'lmstudio', model: 'qwen-world' },
  plan: {},
  progress: { percent: 100, active_topic_ids: [], failed_topic_ids: [] },
  error: {},
  created_at: '2026-07-20T00:00:00Z',
  updated_at: '2026-07-20T00:00:00Z',
};

const approvedProfileResponse = {
  ok: true,
  review: {
    world_id: 'world:aurelia',
    status: 'approved',
    profile_revision: 1,
    profile_hash: 'sha256:profile',
    approved_profile_hash: 'sha256:profile',
    approved_at: '2026-07-20T00:00:00Z',
    approved_by: 'local-author',
    requested_genre: 'fantasy',
    normalized_genre: 'classic_fantasy',
    source: 'registry',
    generated: false,
    route: {},
    review_findings: [],
    error: {},
    profile: {
      profile_id: 'classic_fantasy',
      version: 2,
      display_name: 'Classic fantasy',
      domains: [
        {
          domain_id: 'regions',
          title: 'Realms, Regions and Wild Frontiers',
          entity_kind: 'region',
          dependencies: [],
          required_before_launch: true,
          fields: [],
          target_range: { quick: [2, 4], standard: [5, 8], epic: [9, 14] },
          semantic_roles: [],
          generation_guidance: {
            presentation: {
              page_kind: 'collection',
              card_variant: 'regions',
              image_role: 'landscape',
              group: 'world',
            },
          },
        },
      ],
    },
  },
};

function renderDashboard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <RpgWorldGenerationDashboard
        generation={previousRun}
        sections={[section]}
        worldId="world:aurelia"
      />
    </QueryClientProvider>,
  );
}

describe('RpgWorldGenerationDashboard', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('starts generation from the prominent action after the profile is approved', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      requests.push({ url, init });
      if (url.endsWith('/genre-profile')) {
        return new Response(JSON.stringify(approvedProfileResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      return new Response(JSON.stringify({
        ok: true,
        worker_started: true,
        run: {
          ...previousRun,
          run_id: 'run:new',
          status: 'running',
          progress: { percent: 0, active_topic_ids: ['regions'], failed_topic_ids: [] },
          settings: { provider_route: 'lmstudio', model: 'qwen-world' },
        },
        execution_summary: {
          queued_count: 1,
          reused_count: 0,
          protected_count: 0,
        },
        resolved_route: {
          provider: 'lmstudio',
          model: 'qwen-world',
          source: 'settings_control_center',
        },
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }));

    renderDashboard();
    const generate = await screen.findByRole('button', { name: '✦ Generate World' });
    await waitFor(() => expect(generate).toBeEnabled());
    fireEvent.click(generate);

    await waitFor(() => expect(requests.some((request) => request.url.includes('/generation'))).toBe(true));
    expect(generate).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText(/Generate World selected\. Generation controls are open below/)).toBeInTheDocument();
    const generationRequest = requests.find((request) => request.url.includes('/generation'));
    expect(generationRequest?.url).toContain('/api/rpg/worlds/world%3Aaurelia/generation');
    expect(JSON.parse(String(generationRequest?.init?.body))).toMatchObject({
      scope: { mode: 'full' },
      provider_route: 'configured',
      model: 'configured',
    });
    expect(await screen.findByText(/1 provider topic job queued/)).toBeInTheDocument();
  });

  it('enables continuation for an approved partial review run', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(approvedProfileResponse), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })));
    const partialReviewRun = {
      ...previousRun,
      graph: { nodes: [{ topic_id: 'realm' }, { topic_id: 'places' }] },
      plan: { topic_ids: ['realm'] },
    };
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <RpgWorldGenerationDashboard generation={partialReviewRun} sections={[section]} worldId="world:aurelia" />
      </QueryClientProvider>,
    );

    await screen.findByText('Profile Approved');
    expect(screen.getAllByRole('button', { name: 'Continue Generation' })).toEqual(
      expect.arrayContaining([expect.objectContaining({ disabled: false })]),
    );
  });

  it('keeps prominent generation actions locked for an unapproved profile', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      ...approvedProfileResponse,
      review: {
        ...approvedProfileResponse.review,
        status: 'review_required',
        approved_profile_hash: '',
      },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })));

    renderDashboard();

    expect(await screen.findByText('Review Required')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '✦ Generate World' })).toBeDisabled();
    expect(screen.getByText(/Generation is locked while the profile is awaiting approval/)).toBeInTheDocument();
  });

  it('shows provider-reported and estimated world-generation token usage', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(approvedProfileResponse), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })));
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <RpgWorldGenerationDashboard
          generation={previousRun}
          sections={[section]}
          tokenUsage={{
            prompt_tokens: 12_000,
            completion_tokens: 3_000,
            total_tokens: 15_000,
            provider_reported_topics: 3,
            estimated_topics: 1,
            unavailable_topics: 0,
            topic_count: 4,
            in_flight_topics: 1,
          }}
          worldId="world:aurelia"
        />
      </QueryClientProvider>,
    );

    expect(screen.getByRole('region', { name: 'World generation token usage' })).toHaveTextContent('15,000');
    expect(screen.getByText(/4 completed/)).toBeInTheDocument();
    expect(screen.getByText(/live batches included/i)).toBeInTheDocument();
    expect(screen.getByText('3 provider-reported · 1 estimated')).toBeInTheDocument();
    await screen.findByText('Profile Approved');
  });
});
