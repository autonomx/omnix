import { Badge, Box, Group, NavLink, Paper, Progress, Stack, Text, Title } from '@mantine/core';
import type { ReactNode } from 'react';

export function OmnixShellLayout({ sidebar, topbar, children }: { sidebar: ReactNode; topbar: ReactNode; children: ReactNode }) {
  return (
    <Box className="omnix-shell">
      {sidebar}
      <main className="omnix-main">
        {topbar}
        {children}
      </main>
    </Box>
  );
}

export function OmnixSidebar({ children }: { children: ReactNode }) {
  return (
    <aside className="omnix-sidebar" aria-label="Omnix modules">
      {children}
    </aside>
  );
}

export function OmnixBrand() {
  return (
    <Group className="omnix-brand" gap="sm">
      <span className="omnix-brand-mark">O</span>
      <div>
        <Title order={1}>Omnix</Title>
        <Text size="sm">AI workstation</Text>
      </div>
    </Group>
  );
}

export function OmnixNavItem({ active, children }: { active: boolean; children: ReactNode }) {
  return (
    <NavLink className={active ? 'active' : undefined} active={active} label={children} component="span" />
  );
}

export function OmnixTopBar({ title, status = 'Local-first' }: { title: string; status?: string }) {
  return (
    <header className="omnix-topbar">
      <div>
        <Text className="eyebrow">Shared Omnix platform</Text>
        <Title order={2}>{title}</Title>
      </div>
      <OmnixStatusPill>{status}</OmnixStatusPill>
    </header>
  );
}

export function OmnixStatusPill({ children }: { children: ReactNode }) {
  return (
    <Badge className="status-pill" variant="light">
      {children}
    </Badge>
  );
}

export function WorkspacePanel({ children }: { children: ReactNode }) {
  return (
    <Paper className="workspace-card" component="section" aria-labelledby="module-title">
      {children}
    </Paper>
  );
}

export function OmnixProgressLog({
  value,
  logs,
}: {
  value: number;
  logs: Array<{ level: string; message: string }>;
}) {
  return (
    <Stack gap="xs">
      <Progress value={value} aria-label="Progress" />
      <Stack className="omnix-log-viewer" gap={4}>
        {logs.map((log, index) => (
          <Text key={`${log.level}-${index}`} size="sm">
            <strong>{log.level}</strong> {log.message}
          </Text>
        ))}
      </Stack>
    </Stack>
  );
}

export function OmnixTranscriptView({ messages }: { messages: Array<{ role: string; content: string }> }) {
  return (
    <Stack className="omnix-transcript" gap="xs">
      {messages.map((message, index) => (
        <Paper key={`${message.role}-${index}`} className="omnix-message" component="article">
          <Text size="xs" tt="uppercase">
            {message.role}
          </Text>
          <Text>{message.content}</Text>
        </Paper>
      ))}
    </Stack>
  );
}

export function OmnixAudioControls({ label }: { label: string }) {
  return (
    <Group className="omnix-audio-controls" gap="sm">
      <button type="button" aria-label={`Play ${label}`}>
        Play
      </button>
      <button type="button" aria-label={`Stop ${label}`}>
        Stop
      </button>
      <Text size="sm">{label}</Text>
    </Group>
  );
}

export function OmnixAssetCard({ title, metadata }: { title: string; metadata: string }) {
  return (
    <Paper className="omnix-asset-card" component="article">
      <Title order={4}>{title}</Title>
      <Text size="sm">{metadata}</Text>
    </Paper>
  );
}

export function OmnixDiagnosticsView({ rows }: { rows: Array<{ label: string; value: string }> }) {
  return (
    <Stack className="omnix-diagnostics" gap="xs">
      {rows.map((row) => (
        <Group key={row.label} justify="space-between">
          <Text size="sm">{row.label}</Text>
          <OmnixStatusPill>{row.value}</OmnixStatusPill>
        </Group>
      ))}
    </Stack>
  );
}
