import { Button, Group, Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { omnixApiClient, type SettingsPayload } from '../../api/client';
import { OmnixStatusPill } from '../../design/primitives';

type HermesStatus = {
  enabled?: boolean;
  reachable?: boolean;
  base_url?: string;
  error?: string | null;
};

type HermesSettingsPayload = SettingsPayload & {
  hermes_status?: HermesStatus;
  hermes_commands?: Record<string, string>;
};

function valueText(value: unknown): string {
  return value === undefined || value === null || value === '' ? 'unknown' : String(value);
}

function rows(status: HermesStatus, commands: Record<string, string>): Array<[string, string]> {
  return [
    ['Base URL', valueText(status.base_url)],
    ['Error', valueText(status.error)],
    ['Configure later', valueText(commands.configure)],
    ['Enable env', valueText(commands.enable_env)],
  ];
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
  const statusText = status.enabled ? (status.reachable ? 'reachable' : 'offline') : 'disabled';

  return (
    <section className="platform-section platform-section-wide">
      <Group justify="space-between" align="start">
        <div>
          <Title order={4}>Hermes Agent</Title>
          <Text size="sm">Sidecar status, setup commands, and a safe dry-run Agent Chat smoke test.</Text>
        </div>
        <OmnixStatusPill>{query.isLoading ? 'loading' : statusText}</OmnixStatusPill>
      </Group>
      {query.isError ? <Text role="alert">Hermes status failed: {query.error.message}</Text> : null}
      <Details rows={rows(status, commands)} />
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
