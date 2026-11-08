/** What a character or the System Assistant may do in calls, such as look things up on the web: one switch each. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { abilitiesClient } from './abilitiesClient';
import './OwnerAbilitiesPanel.css';

export function OwnerAbilitiesPanel({ ownerId, ownerName }: { ownerId: string; ownerName: string }) {
  const queryClient = useQueryClient();
  const queryKey = ['feature', 'chatbot', 'owner-abilities', ownerId];
  const abilitiesQuery = useQuery({ queryKey, queryFn: () => abilitiesClient.read(ownerId) });
  const change = useMutation({
    mutationFn: ({ abilityId, granted }: { abilityId: string; granted: boolean }) =>
      abilitiesClient.set(ownerId, abilityId, granted),
    onSuccess: (payload) => queryClient.setQueryData(queryKey, payload),
  });

  return <section className="character-dashboard-section character-memory-section" aria-label={`${ownerName} abilities`}>
    <header className="character-section-heading"><div><h4>What {ownerName} can do in calls</h4></div></header>
    <p className="character-memory-intro">
      {ownerName} uses these only when you ask about the real world, and only those you turn on here.
    </p>
    {abilitiesQuery.isError ? <p className="character-memory-error" role="alert">
      Abilities could not be loaded.{' '}
      <button type="button" onClick={() => void abilitiesQuery.refetch()} disabled={abilitiesQuery.isFetching}>Try again</button>
    </p> : null}
    {change.isError ? <p className="character-memory-error" role="alert">The change was not saved.</p> : null}
    {(abilitiesQuery.data?.abilities ?? []).map((ability) => (
      <label key={ability.id} className="character-ability">
        <input
          type="checkbox"
          checked={ability.granted}
          disabled={change.isPending}
          onChange={(event) => change.mutate({ abilityId: ability.id, granted: event.currentTarget.checked })}
        />
        {' '}{ability.label}
      </label>
    ))}
  </section>;
}
