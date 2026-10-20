import { describe, expect, it } from 'vitest';
import { dubbingModule } from './module';

describe('Dubbing module', () => {
  it('serves the dubbing backend module under its own API prefix', () => {
    expect(dubbingModule.id).toBe('dubbing');
    expect(dubbingModule.backendModules).toEqual(['dubbing']);
    expect(dubbingModule.apiPrefixes).toEqual(['/api/dubbing']);
  });
});
