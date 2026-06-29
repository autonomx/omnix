import { Text, Title } from '@mantine/core';
import { useQuery } from '@tanstack/react-query';
import { getHermesRecent } from '../../api/hermesClient';

export function HermesRecentPanel() {
  const query = useQuery({
    queryKey: ['platform', 'hermes-recent'],
    queryFn: () => getHermesRecent(),
    retry: false,
  });
  const items = query.data?.items ?? [];

  return (
    <section className="platform-section">
      <Title order={5}>Hermes recent</Title>
      <Text size="sm">Compact Hermes recent-item surface for diagnostics and later storage wiring.</Text>
      {query.isError ? <Text role="alert">Recent surface unavailable: {query.error.message}</Text> : null}
      <dl className="platform-details">
        <div>
          <dt>Source</dt>
          <dd>{query.data?.source ?? 'checking'}</dd>
        </div>
        <div>
          <dt>Count</dt>
          <dd>{query.isLoading ? 'loading' : String(query.data?.count ?? items.length)}</dd>
        </div>
      </dl>
      {items.length === 0 ? <Text size="sm">No recent Hermes items reported yet.</Text> : null}
    </section>
  );
}
