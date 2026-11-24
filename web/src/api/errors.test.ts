import { describe, expect, it } from 'vitest';

import { ApiError } from './errors';

describe('ApiError', () => {
  it("keeps the response's Retry-After in milliseconds when it is a number of seconds", () => {
    expect(new ApiError(409, '{"detail":"initiative_spacing"}', 'r1', '12').retryAfterMs).toBe(12_000);
    expect(new ApiError(409, '{"detail":"initiative_spacing"}', 'r1', '12').detail).toBe('initiative_spacing');
    expect(new ApiError(409, '', 'r1', 'Wed, 21 Oct 2026 07:28:00 GMT').retryAfterMs).toBeUndefined();
    expect(new ApiError(409, '', 'r1').retryAfterMs).toBeUndefined();
    expect(new ApiError(409, '', 'r1', null).retryAfterMs).toBeUndefined();
  });
});
