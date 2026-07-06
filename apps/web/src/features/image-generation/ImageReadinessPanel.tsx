import { Button, Group, Text } from '@mantine/core';
import { OmnixStatusPill } from '../../design/primitives';
import type { ImageReadiness } from './imageReadinessModel';

interface ImageReadinessPanelProps {
  readiness: ImageReadiness;
  refreshing: boolean;
  onRefresh: () => void;
}

export function ImageReadinessPanel({ readiness, refreshing, onRefresh }: ImageReadinessPanelProps) {
  return (
    <div className="feature-mini-card" role="status" aria-live="polite">
      <Group justify="space-between" align="start">
        <div>
          <strong>{readiness.title}</strong>
          <Text size="sm">{readiness.message}</Text>
          <Text size="xs" mt="xs">Mode: {readiness.workerMode} / Ready providers: {readiness.providerCount}</Text>
        </div>
        <OmnixStatusPill>{readiness.status}</OmnixStatusPill>
      </Group>
      <Group gap="xs" mt="sm">
        <Button component="a" href="/settings" size="xs" variant="light">Open Settings</Button>
        <Button component="a" href="/diagnostics" size="xs" variant="default">Open Diagnostics</Button>
        <Button loading={refreshing} onClick={onRefresh} size="xs" variant="subtle">Refresh status</Button>
      </Group>
    </div>
  );
}
