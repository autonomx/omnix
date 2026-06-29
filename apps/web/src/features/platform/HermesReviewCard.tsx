import { useState } from 'react';
import { Button, Group, Text, Title } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { approveHermesCandidate, getHermesCandidateDemo } from '../../api/hermesClient';

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

function previewValue(value: Record<string, unknown> | undefined): string {
  return value ? JSON.stringify(value) : 'none';
}

export function HermesReviewCard({
  title = 'Hermes review',
  summary = 'Hermes suggestions are shown here for inspection only.',
  area = 'Settings',
  item = 'No suggestion selected',
  details = 'Read-only preview mode is active for this card.',
  state = 'preview-only',
}: HermesReviewCardProps) {
  const [candidateVisible, setCandidateVisible] = useState(true);
  const [approvalState, setApprovalState] = useState('approvals disabled');
  const [approvalBusy, setApprovalBusy] = useState(false);
  const query = useQuery({
    queryKey: ['platform', 'hermes-candidate-demo'],
    queryFn: () => getHermesCandidateDemo(),
    retry: false,
  });
  const candidate = candidateVisible ? query.data?.candidate : undefined;

  const handleApproval = async () => {
    if (!candidate || approvalBusy) {
      return;
    }
    setApprovalBusy(true);
    setApprovalState('checking approval gate');
    try {
      const payload = await approveHermesCandidate({ candidate, preview_only: true });
      setApprovalState(payload.error ?? 'approvals disabled');
    } catch (error) {
      setApprovalState(error instanceof Error ? error.message : 'approval unavailable');
    } finally {
      setApprovalBusy(false);
    }
  };

  const handleCancel = () => {
    setCandidateVisible(false);
    setApprovalState('preview cleared locally');
  };

  return (
    <section className="platform-section">
      <Title order={5}>{title}</Title>
      <Text size="sm">{summary}</Text>
      {query.isError ? <Text role="alert">Candidate preview unavailable: {query.error.message}</Text> : null}
      <dl className="platform-details">
        <div>
          <dt>Area</dt>
          <dd>{area}</dd>
        </div>
        <div>
          <dt>Item</dt>
          <dd>{candidate?.name ?? item}</dd>
        </div>
        <div>
          <dt>State</dt>
          <dd>{query.isLoading ? 'loading-preview' : state}</dd>
        </div>
        <div>
          <dt>Details</dt>
          <dd>{candidate?.note ?? details}</dd>
        </div>
        <div>
          <dt>Target</dt>
          <dd>{candidate?.target ?? 'none'}</dd>
        </div>
        <div>
          <dt>Before</dt>
          <dd>{previewValue(candidate?.before)}</dd>
        </div>
        <div>
          <dt>After</dt>
          <dd>{previewValue(candidate?.after)}</dd>
        </div>
        <div>
          <dt>Risk</dt>
          <dd>{candidate?.risk ?? 'blocked'}</dd>
        </div>
        <div>
          <dt>Preview only</dt>
          <dd>{String(query.data?.preview_only ?? true)}</dd>
        </div>
        <div>
          <dt>Approval</dt>
          <dd>{approvalBusy ? 'checking' : approvalState}</dd>
        </div>
        {policyRows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <Group gap="xs">
        <Button size="xs" variant="light" onClick={handleApproval} disabled={!candidate || approvalBusy}>
          Approve
        </Button>
        <Button size="xs" variant="subtle" onClick={handleCancel} disabled={!candidateVisible}>
          Cancel preview
        </Button>
      </Group>
    </section>
  );
}
