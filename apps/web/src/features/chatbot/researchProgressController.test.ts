import { beforeAll, describe, expect, it } from 'vitest';
import type { ChatSession, JobRecord } from '../../api/client';

type TestWindow = Window & Record<string, unknown>;

let helpers: typeof import('./researchProgressController');

beforeAll(async () => {
  (window as unknown as TestWindow).__omnix_research_progress_controller__ = true;
  helpers = await import('./researchProgressController');
});

function researchJob(overrides: Partial<JobRecord> = {}): JobRecord {
  return {
    id: 'job:research-one',
    module: 'assistant',
    type: 'assistant.deep_research',
    status: 'running',
    resource_class: 'network',
    priority: 0,
    stages: [
      {
        id: 'planning',
        label: 'Planning research',
        status: 'completed',
        resource_class: 'cpu',
        progress: { current: 1, total: 1, message: 'completed' },
        output_refs: [],
        retry: { attempts: 0, max_attempts: 0, policy: 'none' },
      },
      {
        id: 'searching',
        label: 'Searching the web',
        status: 'running',
        resource_class: 'network',
        progress: { current: 0, total: 1, message: 'Searching: current release' },
        output_refs: [],
        retry: { attempts: 0, max_attempts: 0, policy: 'none' },
      },
      {
        id: 'synthesizing',
        label: 'Writing the answer',
        status: 'queued',
        resource_class: 'network',
        progress: { current: 0, total: 1 },
        output_refs: [],
        retry: { attempts: 0, max_attempts: 0, policy: 'none' },
      },
    ],
    progress: { current: 1, total: 3, message: 'Searching: current release' },
    logs: [],
    output_refs: [],
    created_at: '2026-07-07T00:00:00Z',
    updated_at: '2026-07-07T00:00:01Z',
    cancel: { requested: false },
    compat: {},
    ...overrides,
  } as JobRecord;
}

function researchSession(): ChatSession {
  return {
    id: 'chat:one',
    title: 'Research chat',
    message_count: 1,
    created_at: '2026-07-07T00:00:00Z',
    updated_at: '2026-07-07T00:00:01Z',
    messages: [
      {
        id: 'msg:user',
        role: 'user',
        content: 'Research this',
        created_at: '2026-07-07T00:00:01Z',
        metadata: {
          research_mode: 'deep',
          research_status: 'queued',
          research_job_id: 'job:research-one',
        },
      },
    ],
  } as ChatSession;
}

describe('research progress restoration', () => {
  it('recovers the durable job ID from persisted chat metadata', () => {
    expect(helpers.latestResearchJobId(researchSession().messages ?? [])).toBe('job:research-one');
  });

  it('uses the active stage label and bounded operational announcement', () => {
    const job = researchJob();
    expect(helpers.researchStageLabel(job)).toBe('Searching the web');
    expect(helpers.researchStageAnnouncement(job)).toBe('Searching: current release');
    expect(helpers.researchStageAnnouncement(job)).not.toContain('reasoning');
    expect(helpers.isActiveResearchJob(job)).toBe(true);
  });

  it('calculates progress from completed stages and caps active jobs below 100 percent', () => {
    expect(helpers.researchProgressPercent(researchJob())).toBe(33);
    expect(helpers.researchProgressPercent(researchJob({ status: 'completed' }))).toBe(100);
  });

  it('announces cancellation and completion without internal planner details', () => {
    const canceling = researchJob({ status: 'cancel_requested' });
    const complete = researchJob({ status: 'completed' });
    expect(helpers.researchStageAnnouncement(canceling)).toContain('Cancellation requested');
    expect(helpers.researchStageAnnouncement(complete)).toContain('Research complete');
    expect(helpers.isActiveResearchJob(complete)).toBe(false);
  });

  it('announces limited evidence for completed jobs with empty research output', () => {
    const complete = researchJob({
      status: 'completed',
      output_refs: [
        {
          type: 'research',
          research_status: 'partial',
          stop_reason: 'no_reliable_sources',
          research_provider: 'duckduckgo',
          search_diagnostics: [
            {
              query: 'rtx 4090 coding llm',
              provider: 'duckduckgo',
              status: 'empty',
              results: 0,
            },
          ],
          warnings: ['limited_search_provider', 'quick_search_empty'],
        },
      ],
    });
    const panel = document.createElement('section');

    expect(helpers.researchStageAnnouncement(complete)).toContain('limited evidence');
    helpers.renderJobPanel(panel, complete);
    expect(panel.textContent).toContain('Search diagnostics');
    expect(panel.textContent).toContain('rtx 4090 coding llm');
    expect(panel.textContent).toContain('0 results');
  });

  it('renders a close button for completed progress panels', () => {
    const panel = document.createElement('section');
    document.body.append(panel);

    helpers.renderJobPanel(panel, researchJob({ status: 'completed' }));
    const close = panel.querySelector<HTMLButtonElement>('[data-omnix-research-close]');

    expect(close).not.toBeNull();
    close?.click();
    expect(document.body.contains(panel)).toBe(false);
  });

  it('keeps active progress panels focused on cancellation instead of dismissal', () => {
    const panel = document.createElement('section');
    document.body.append(panel);

    helpers.renderJobPanel(panel, researchJob());

    expect(panel.querySelector('[data-omnix-research-close]')).toBeNull();
    expect(panel.querySelector('[data-omnix-research-cancel]')).not.toBeNull();
    panel.remove();
  });
});
