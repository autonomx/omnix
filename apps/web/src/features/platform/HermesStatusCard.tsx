import { Button, Group, Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { omnixApiClient, type SettingsPayload } from '../../api/client';
import { OmnixStatusPill } from '../../design/primitives';

type HermesStatus = {
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
    'Run hermes setup',
    'Run hermes model',
    'Start Hermes sidecar',
    `Set ${valueText(commands.enable_env)}`,
    'Restart Omnix backend',
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
        ['Configure later', valueText(commands.configure)],
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
      ['Base URL env', valueText(commands.base_url_env)],
    ],
    nextSteps: [],
  };
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
      <Text size="sm">Next step</Text>
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
  const dryRun = useMutation({
    mutationFn: async () => {
      const session = await omnixApiClient.createChatSession({ title: 'Hermes dry run' });
      const result = await omnixApiClient.sendChatMessage(session.id, {
        content: 'house status',
        agent_mode: true,
        dry_run: true,
      } as never);
      return result.session.messages?.filter((message) => message.role === 'assistant').at(-1)?.content ?? 'Dry run completed.';
    },
  });

  const status = query.data?.hermes_status ?? {};
  const commands = query.data?.hermes_commands ?? {};
  const view = statusView(status, commands);

  return (
    <section className="platform-section platform-section-wide">
      <Group justify="space-between" align="start">
        <div>
          <Title order={4}>Hermes Agent</Title>
          <Text size="sm">Sidecar status, setup commands, and a safe dry-run Agent Chat smoke test.</Text>
        </div>
        <OmnixStatusPill>{query.isLoading ? 'loading' : view.badge}</OmnixStatusPill>
      </Group>
      {query.isError ? <Text role="alert">Hermes status failed: {query.error.message}</Text> : null}
      <Text size="sm">{view.message}</Text>
      <Details rows={view.rows} />
      <NextSteps steps={view.nextSteps} />
      <Group gap="xs">
        <Button size="xs" variant="light" onClick={() => queryClient.invalidateQueries({ queryKey: ['platform', 'settings'] })}>
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
