import { Button, Group, Text, Title } from '@mantine/core';

export type InfoCardProps = {
  title?: string;
  summary?: string;
  area?: string;
  state?: string;
  primaryLabel?: string;
  secondaryLabel?: string;
  onPrimary?: () => void;
  onSecondary?: () => void;
};

export function InfoCard({
  title = 'Setup',
  summary = 'Check the guidance before continuing.',
  area = 'Settings',
  state = 'pending',
  primaryLabel = 'Done',
  secondaryLabel = 'Dismiss',
  onPrimary,
  onSecondary,
}: InfoCardProps) {
  return (
    <section className="platform-section">
      <Title order={5}>{title}</Title>
      <Text size="sm">{summary}</Text>
      <dl className="platform-details">
        <div>
          <dt>Area</dt>
          <dd>{area}</dd>
        </div>
        <div>
          <dt>State</dt>
          <dd>{state}</dd>
        </div>
      </dl>
      <Group gap="xs">
        <Button size="xs" variant="light" onClick={onPrimary}>
          {primaryLabel}
        </Button>
        <Button size="xs" variant="subtle" onClick={onSecondary}>
          {secondaryLabel}
        </Button>
      </Group>
    </section>
  );
}
