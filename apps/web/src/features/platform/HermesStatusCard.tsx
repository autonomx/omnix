import { Button, Group, Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { omnixApiClient, type SettingsPayload } from '../../api/client';
import { getHermesStatus, runHermesTest, type HermesStatusResponse, type HermesTestResponse } from '../../api/hermesClient';
import { OmnixStatusPill } from '../../design/primitives';

type HermesStatus = HermesStatusResponse & {
  enabled?: boolean;
  reachable?: boolean;
  state?: string;
  message?: string | null;
  base_url?: string;
  health?: Record<string, unknown>;
  capabilities?: Record<string, unknown>;
  error?: string | null;
};

type HermesSettingsPayload = SettingsPayload & {
  hermes_status?: HermesStatus;
  hermes_commands?: Record<string, string>;
};

type StatusView = {
  badge: string;
  message: string;
  rows: Array<[string, string]>;
  nextSteps: string[];
};

function valueText(value: unknown): string {
  return value === undefined || value === null || value === '' ? 'unknown' : String(value);
}

function shortJson(value: unknown): string {
  if (value === undefined || value === null || value === '') {
    return 'unknown';
  }
  if (typeof value === 'string') {
    return value;
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function objectSummary(value: Record<string, unknown> | undefined): string {
  const entries = Object.entries(value ?? {}).filter(([, item]) => item !== undefined && item !== null && item !== '');
  if (entries.length === 0) {
    return 'none reported';
  }
  return entries
    .slice(0, 4)
    .map(([key, item]) => `${key}: ${shortJson(item)}`)
    .join('; ');
}

function setupSteps(commands: Record<string, string>): string[] {
  return [
    `Run ${valueText(commands.setup ?? 'hermes setup')}`,
    `Run ${valueText(commands.model ?? 'hermes model')}`,
    `Start sidecar: ${valueText(commands.start_sidecar ?? 'hermes serve')}`,
    `Set ${valueText(commands.enable_env)}`,
    valueText(commands.restart_backend ?? 'Restart Omnix backend'),
  ];
}

function statusView(status: HermesStatus, commands: Record<string, string>): StatusView {
  const state = status.state ?? (status.enabled ? (status.reachable ? 'reachable' : 'offline') : 'disabled');
  const disabled = state === 'disabled' || (!status.enabled && status.error === 'hermes_disabled') || (!status.enabled && !status.reachable);

  if (disabled) {
    return {
      badge: 'disabled',
      message: status.message ?? 'Installed, disabled in Omnix.',
      rows: [
        ['Base URL', valueText(status.base_url)],
        ['Status', 'Installed, disabled in Omnix'],
        ['Setup', valueText(commands.setup ?? commands.configure)],
        ['Model', valueText(commands.model)],
        ['Start sidecar', valueText(commands.start_sidecar)],
        ['Enable env', valueText(commands.enable_env)],
      ],
      nextSteps: setupSteps(commands),
    };
  }

  if (state === 'reachable' || status.reachable) {
    return {
      badge: 'reachable',
      message: status.message ?? 'Connected to Hermes sidecar.',
      rows: [
        ['Base URL', valueText(status.base_url)],
        ['Status', 'Connected to Hermes sidecar'],
        ['Health', objectSummary(status.health)],
        ['Capabilities', objectSummary(status.capabilities)],
      ],
      nextSteps: [],
    };
  }

  return {
    badge: 'offline',
    message: status.message ?? 'Enabled in Omnix, but the Hermes sidecar is unreachable.',
    rows: [
      ['Base URL', valueText(status.base_url)],
      ['Status', 'Enabled in Omnix, sidecar unreachable'],
      ['Error', valueText(status.error)],
      ['Start sidecar', valueText(commands.start_sidecar)],
      ['Base URL env', valueText(commands.base_url_env)],
    ],
    nextSteps: [],
  };
}

function dryRunText(result: HermesTestResponse): string {
  const response = result.result?.result?.response;
  const prefix = result.dry_run ? 'Dry run' : 'Test';
  const backend = result.result?.backend ? ` via ${result.result.backend}` : '';
  const outcome = result.ok === undefined ? '' : ` Trace: ok=${String(result.ok)}, dry_run=${String(Boolean(result.dry_run))}.`;
  if (response) {
    return `${prefix}${backend}: ${response}${outcome}`;
  }
  if (result.error) {
    return `${prefix}${backend}: ${result.error}${outcome}`;
  }
  return `${prefix}${backend} completed.${outcome}`;
}

function routeLabel(routeStatus: { data?: HermesStatusResponse; isError: boolean; isLoading: boolean }): string {
  if (routeStatus.isError) {
    return 'unavailable';
  }
  if (routeStatus.data) {
    return 'available';
  }
  return routeStatus.isLoading ? 'checking' : 'unknown';
}

function Details({ rows }: { rows: Array<[string, string]> }) {
  return (
    <dl className="platform-details">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function NextSteps({ steps }: { steps: string[] }) {
  if (steps.length === 0) {
    return null;
  }
  return (
    <div>
      <Text size="sm">Next steps</Text>
      <ol>
        {steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
    </div>
  );
}

export function HermesStatusCard() {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ['platform', 'settings'],
    queryFn: () => omnixApiClient.getSettings() as Promise<HermesSettingsPayload>,
  });
  const routeStatus = useQuery({
    queryKey: ['platform', 'hermes-status'],
    queryFn: () => getHermesStatus(),
    retry: false,
  });
  const dryRun = useMutation({
    mutationFn: async () => {
      try {
        const result = await runHermesTest({ content: 'house status', dry_run: true });
        return dryRunText(result);
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Hermes test route unavailable.';
        return `Dry-run route unavailable: ${message}`;
      }
    },
  });

  const status = (routeStatus.data as HermesStatus | undefined) ?? query.data?.hermes_status ?? {};
  const commands = query.data?.hermes_commands ?? {};
  const view = statusView(status, commands);
  const rows: Array<[string, string]> = [['Route', routeLabel(routeStatus)], ...view.rows];

  return (
    <section className="platform-section platform-section-wide">
      <Group justify="space-between" align="start">
        <div>
          <Title order={4}>Hermes Agent</Title>
          <Text size="sm">Sidecar status, setup commands, and a safe dry-run Agent Chat smoke test.</Text>
        </div>
        <OmnixStatusPill>{query.isLoading || routeStatus.isLoading ? 'loading' : view.badge}</OmnixStatusPill>
      </Group>
      {query.isError ? <Text role="alert">Hermes status failed: {query.error.message}</Text> : null}
      {routeStatus.isError ? <Text role="alert">Hermes route unavailable: {routeStatus.error.message}</Text> : null}
      <Text size="sm">{view.message}</Text>
      <Details rows={rows} />
      <NextSteps steps={view.nextSteps} />
      <Group gap="xs">
        <Button
          size="xs"
          variant="light"
          onClick={() => {
            queryClient.invalidateQueries({ queryKey: ['platform', 'settings'] });
            queryClient.invalidateQueries({ queryKey: ['platform', 'hermes-status'] });
          }}
        >
          Refresh
        </Button>
        <Button size="xs" variant="light" loading={dryRun.isPending} onClick={() => dryRun.mutate()}>
          Run dry-run test
        </Button>
      </Group>
      {dryRun.isError ? <Text role="alert">Dry-run failed: {dryRun.error.message}</Text> : null}
      {dryRun.data ? <Text role="status">{dryRun.data}</Text> : null}
    </section>
  );
}
