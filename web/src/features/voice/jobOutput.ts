import type { JobRecord } from '../../api/client';

/** The first output reference of a finished job. */
export function firstOutput(job: JobRecord | undefined): Record<string, unknown> | undefined {
  const refs = (job?.output_refs ?? []) as unknown as Array<Record<string, unknown>>;
  return refs[0];
}
