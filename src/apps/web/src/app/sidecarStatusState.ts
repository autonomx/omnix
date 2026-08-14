export type SidecarStatusStateName = 'idle' | 'loading' | 'ready' | 'error' | 'disabled';

export interface SidecarStatusStateInput {
  loading?: boolean;
  payload?: { ok?: boolean; status?: string; enabled?: boolean } | null;
  error?: string | null;
}

export interface SidecarStatusState {
  status: SidecarStatusStateName;
  message: string;
  readOnly: true;
  executes: false;
}

export function createSidecarStatusState(input: SidecarStatusStateInput = {}): SidecarStatusState {
  if (input.loading) {
    return { status: 'loading', message: 'Checking status.', readOnly: true, executes: false };
  }
  if (input.error) {
    return { status: 'error', message: input.error, readOnly: true, executes: false };
  }
  if (input.payload?.enabled === false || input.payload?.status === 'disabled') {
    return { status: 'disabled', message: 'Service is disabled.', readOnly: true, executes: false };
  }
  if (input.payload?.ok === true) {
    return { status: 'ready', message: input.payload.status || 'Ready.', readOnly: true, executes: false };
  }
  return { status: 'idle', message: 'Status not requested.', readOnly: true, executes: false };
}
