import type { RpgLiveDataStatusCard } from './RpgLiveDataStatus';
import { formatQueryError } from './rpgWorkspaceSupport';

/** What a source's query is doing, as the live-data panel reads it. */
interface QueryStatus {
  data?: unknown;
  error: unknown;
  isError: boolean;
  isFetching: boolean;
  isPending: boolean;
}

interface SourceText {
  loading: string;
  refreshing: string;
  ready: string;
  empty: string;
}

function sourceCard(id: string, label: string, query: QueryStatus, count: number, text: SourceText): RpgLiveDataStatusCard {
  const loading = query.isPending && !query.data;
  const refreshing = query.isFetching && Boolean(query.data);
  const state = query.isError ? 'error' : loading ? 'loading' : refreshing ? 'refreshing' : count ? 'ready' : 'empty';
  const detail = query.isError ? formatQueryError(query.error) : text[state === 'error' ? 'empty' : state];
  return { id, label, state, detail };
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`;
}

/** The live-data panel (Developer tools): where the play screen's sessions, jobs, assets and reports come from. */
export function buildRpgLiveDataCards(sources: {
  inventory: QueryStatus;
  sessionCount: number;
  jobs: QueryStatus;
  jobCount: number;
  assets: QueryStatus;
  assetCount: number;
  reports: QueryStatus;
  reportCount: number;
}): RpgLiveDataStatusCard[] {
  return [
    sourceCard('sessions', 'Sessions', sources.inventory, sources.sessionCount, {
      loading: 'Loading replay persistence inventory and campaign sessions.',
      refreshing: 'Refreshing the selected session and checkpoint metadata.',
      ready: `${plural(sources.sessionCount, 'saved session')} available.`,
      empty: 'No saved RPG sessions found. Preview fallback remains active until a campaign is created.',
    }),
    sourceCard('jobs', 'Jobs', sources.jobs, sources.jobCount, {
      loading: 'Loading shared job queue state for RPG turns and autoplay.',
      refreshing: 'Polling background RPG jobs.',
      ready: `${plural(sources.jobCount, 'RPG job')} visible in the workspace.`,
      empty: 'No live RPG jobs. Preview job cards keep the rail layout stable.',
    }),
    sourceCard('checkpoints', 'Checkpoints', sources.assets, sources.assetCount, {
      loading: 'Loading RPG checkpoint and report assets.',
      refreshing: 'Refreshing asset metadata for checkpoint/report links.',
      ready: `${plural(sources.assetCount, 'RPG asset')} found for checkpoints or reports.`,
      empty: 'No RPG checkpoint/report assets found yet.',
    }),
    sourceCard('reports', 'Reports', sources.reports, sources.reportCount, {
      loading: 'Loading generated report index.',
      refreshing: 'Refreshing RPG report availability.',
      ready: `${plural(sources.reportCount, 'RPG report')} ready to open.`,
      empty: 'No RPG reports found. Run autoplay or export a report to populate this source.',
    }),
  ];
}
