import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, omnixApiClient, type CreateJobRequest } from '../../../api/client';
import { rpgSessionClient } from './rpgSessionClient';

const turnRequest = {
  module: 'rpg',
  type: 'rpg.turn',
  resource_class: 'gpu:llm',
  priority: 0,
  input_ref: { session_id: 'session-1' },
  input_payload: { command: 'look around' },
} as unknown as CreateJobRequest;

describe('rpgSessionClient.submitTurnJob', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('applies the turn through the foreground session route', async () => {
    const post = vi.spyOn(omnixApiClient, 'post').mockResolvedValue({ ok: true, content: 'You see a door.' });
    const createJob = vi.spyOn(omnixApiClient, 'createJob');

    const job = await rpgSessionClient.submitTurnJob(turnRequest);

    expect(post).toHaveBeenCalledWith('/api/rpg/sessions/session-1/turn', { command: 'look around' });
    expect(createJob).not.toHaveBeenCalled();
    expect(job).toMatchObject({ module: 'rpg', type: 'rpg.turn', status: 'completed' });
    expect(job.id).toMatch(/^foreground:rpg\.turn:/);
  });

  it('queues an ordinary job when the foreground route is missing', async () => {
    vi.spyOn(omnixApiClient, 'post').mockRejectedValue(new ApiError(404, 'not found'));
    const queued = { id: 'job-1' };
    const createJob = vi.spyOn(omnixApiClient, 'createJob').mockResolvedValue(queued as never);

    await expect(rpgSessionClient.submitTurnJob(turnRequest, { timeoutMs: 5 })).resolves.toBe(queued);
    expect(createJob).toHaveBeenCalledWith(turnRequest, { timeoutMs: 5 });
  });

  it('queues a turn without a session as an ordinary job', async () => {
    const post = vi.spyOn(omnixApiClient, 'post');
    const createJob = vi.spyOn(omnixApiClient, 'createJob').mockResolvedValue({ id: 'job-2' } as never);
    const request = { ...turnRequest, input_ref: null } as unknown as CreateJobRequest;

    await rpgSessionClient.submitTurnJob(request);

    expect(post).not.toHaveBeenCalled();
    expect(createJob).toHaveBeenCalledWith(request, {});
  });
});

describe('OmnixApiClient.createJob', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('posts every job, including an RPG turn, to the jobs route', async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => Response.json({ id: 'job-3' }));
    vi.stubGlobal('fetch', fetchMock);

    await omnixApiClient.createJob(turnRequest);

    const paths = fetchMock.mock.calls.map(([input]) => new URL(String(input instanceof Request ? input.url : input), 'http://localhost').pathname);
    expect(paths).toEqual(['/api/jobs']);
  });
});
