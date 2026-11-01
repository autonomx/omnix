import { useQuery } from '@tanstack/react-query';
import { rpgSessionClient, type RpgOperationsResponse } from './api/rpgSessionClient';
import './RpgOperationsPanel.css';

type OperationsDay = RpgOperationsResponse['days'][number];

const percent = (value: number) => `${(value * 100).toFixed(1)}%`;
const milliseconds = (value: number | null | undefined) => (value == null ? '—' : `${Math.round(value)} ms`);

/** The workspace's turns by day (RQ-8.4), in Developer tools: how many failed or degraded, and how long they took. */
export function RpgOperationsPanel({ days = 14 }: { days?: number }) {
  const query = useQuery({
    queryKey: ['feature', 'rpg', 'operations', days],
    queryFn: () => rpgSessionClient.getRpgOperations(days),
    refetchInterval: 60_000,
  });
  const rows: OperationsDay[] = query.data?.days ?? [];
  return (
    <section className="rpg-operations" aria-label="Turn operations">
      <h3>Turns, last {days} days</h3>
      {query.isError ? <p role="alert">The turn record could not be read.</p> : null}
      {!query.isError && !rows.length ? <p>{query.isPending ? 'Reading the turn record…' : 'No turns recorded yet.'}</p> : null}
      {rows.length ? (
        <table>
          <thead>
            <tr>
              <th scope="col">Day</th>
              <th scope="col">Turns</th>
              <th scope="col">Failed</th>
              <th scope="col">Degraded</th>
              <th scope="col">Model calls a turn</th>
              <th scope="col">Slowest class (p95)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const slowest = [...row.classes].sort((a, b) => (b.p95_ms ?? 0) - (a.p95_ms ?? 0))[0];
              return (
                <tr key={row.day}>
                  <th scope="row">{row.day}</th>
                  <td>{row.turns}</td>
                  <td>{row.failed} ({percent(row.failure_rate)})</td>
                  <td>{row.degraded} ({percent(row.degraded_rate)})</td>
                  <td>{row.model_calls_per_turn.toFixed(2)}</td>
                  <td>{slowest ? `${slowest.turn_class}: ${milliseconds(slowest.p95_ms)}` : '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : null}
      {rows[0]?.classes.length ? (
        <p className="rpg-operations__classes">
          {rows[0].day}: {rows[0].classes.map((row) => `${row.turn_class} ${row.turns}× p50 ${milliseconds(row.p50_ms)}`).join(' · ')}
        </p>
      ) : null}
    </section>
  );
}
