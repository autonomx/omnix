import { Button, Group, Text, Title } from '@mantine/core';

export type HermesReviewCardProps = {
  title?: string;
  summary?: string;
  area?: string;
  item?: string;
  details?: string;
  state?: string;
};

const policyRows: Array<[string, string]> = [
  ['Default', 'blocked'],
  ['Read-only names', 'house status, Hermes status, diagnostics schema'],
  ['Review', 'required before any future change path'],
  ['Limits', 'small responses, bounded timeouts, feature flags off by default'],
];

export function HermesReviewCard({
  title = 'Hermes review',
  summary = 'Hermes suggestions are shown here for inspection only.',
  area = 'Settings',
  item = 'No suggestion selected',
  details = 'Read-only preview mode is active for this card.',
  state = 'preview-only',
}: HermesReviewCardProps) {
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
          <dt>Item</dt>
          <dd>{item}</dd>
        </div>
        <div>
          <dt>State</dt>
          <dd>{state}</dd>
        </div>
        <div>
          <dt>Details</dt>
          <dd>{details}</dd>
        </div>
        {policyRows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <Group gap="xs">
        <Button size="xs" variant="light" disabled>
          Preview only
        </Button>
        <Button size="xs" variant="subtle" disabled>
          Close preview
        </Button>
      </Group>
    </section>
  );
}
