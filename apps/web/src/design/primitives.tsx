import { Badge, Box, Group, Paper, Progress, Stack, Text, Title } from '@mantine/core';
import { useState, type ReactNode } from 'react';
import type { OmnixModuleId } from '../app/modules';

export function OmnixShellLayout({
  children,
  isSidebarVisible = true,
  sidebar,
  topbar,
}: {
  children: ReactNode;
  isSidebarVisible?: boolean;
  sidebar: ReactNode;
  topbar: ReactNode;
}) {
  const shellClassName = isSidebarVisible ? 'omnix-shell' : 'omnix-shell sidebar-hidden';

  return (
    <Box className={shellClassName}>
      {sidebar}
      <main className="omnix-main">
        {topbar}
        {children}
      </main>
    </Box>
  );
}

export function OmnixSidebar({ children, hidden = false }: { children: ReactNode; hidden?: boolean }) {
  const [expanded, setExpanded] = useState(true);
  const sidebarClassName = [expanded ? 'omnix-sidebar expanded' : 'omnix-sidebar collapsed', hidden ? 'hidden' : '']
    .filter(Boolean)
    .join(' ');

  return (
    <aside id="omnix-sidebar" className={sidebarClassName} aria-hidden={hidden} aria-label="Omnix navigation">
      <button
        className="omnix-sidebar-toggle"
        type="button"
        aria-label={expanded ? 'Collapse sidebar' : 'Expand sidebar'}
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
      >
        <span aria-hidden="true">☰</span>
      </button>
      {children}
    </aside>
  );
}

export function OmnixBrand() {
  return (
    <div className="omnix-brand" aria-label="Omnix">
      <span className="omnix-brand-mark">O</span>
      <span className="omnix-brand-copy">
        <strong>Omnix</strong>
        <small>Chats</small>
      </span>
    </div>
  );
}

const moduleMonograms: Record<OmnixModuleId, string> = {
  chatbot: 'C',
  rpg: 'R',
  storyteller: 'S',
  podcast: 'P',
  voice: 'T',
  'voice-cloning': 'VC',
  stt: 'ST',
  'image-generation': 'I',
  providers: 'PR',
  models: 'M',
  jobs: 'J',
  assets: 'A',
  reports: 'RP',
  settings: 'SE',
  diagnostics: 'D',
};

export function OmnixNavItem({ active, moduleId, children }: { active: boolean; moduleId: OmnixModuleId; children: ReactNode }) {
  return (
    <span className={active ? 'omnix-nav-item active' : 'omnix-nav-item'}>
      <span className="omnix-nav-icon" aria-hidden="true">
        {moduleMonograms[moduleId]}
      </span>
      <span className="omnix-nav-label">{children}</span>
    </span>
  );
}

export function OmnixTopBar({
  isSidebarVisible = true,
  onToggleSidebar,
  title,
  status = 'Local-first',
  children,
}: {
  isSidebarVisible?: boolean;
  onToggleSidebar?: () => void;
  title: string;
  status?: string;
  children?: ReactNode;
}) {
  return (
    <header className="omnix-topbar">
      <div className="omnix-topbar-brand">
        <button
          className="omnix-logo-core omnix-logo-toggle"
          type="button"
          aria-controls="omnix-sidebar"
          aria-expanded={isSidebarVisible}
          aria-label={isSidebarVisible ? 'Hide Omnix sidebar' : 'Show Omnix sidebar'}
          title={isSidebarVisible ? 'Hide Omnix sidebar' : 'Show Omnix sidebar'}
          onClick={onToggleSidebar}
        />
        <div>
          <Title order={1}>Omnix</Title>
          <Text size="sm">Local AI workstation</Text>
        </div>
      </div>
      {children ? <div className="omnix-mode-tabs">{children}</div> : null}
      <div className="omnix-topbar-status" aria-label="Platform status">
        <OmnixStatusPill>{title}</OmnixStatusPill>
        <OmnixStatusPill>{status}</OmnixStatusPill>
      </div>
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

export function WorkspacePanel({ children, className }: { children: ReactNode; className?: string }) {
  const panelClassName = className ? `workspace-card ${className}` : 'workspace-card';

  return (
    <Paper className={panelClassName} component="section" aria-labelledby="module-title">
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
