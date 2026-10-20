import { Button, Text } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import type { AssetListResponse } from '../../api/client';
import { voiceApiClient, type BatchRun, type ClientCredential, type Recipe, type RecipeStep } from './api/voiceClient';

type Asset = AssetListResponse['assets'][number];

const RECIPES_KEY = ['voice', 'recipes'] as const;
const BATCHES_KEY = ['voice', 'batches'] as const;
const CLIENTS_KEY = ['voice', 'clients'] as const;
const SOURCE_TYPES = new Set(['audio', 'voice_sample', 'voice_take', 'chapter_audio', 'render', 'export']);

/** What each step takes and makes; the gateway checks the same chain (``automation.TOOLS``). */
export const STEP_TOOLS: Record<string, { label: string; takes: 'audio' | 'transcript'; makes: 'audio' | 'transcript' | 'nothing' }> = {
  isolate: { label: 'Isolate vocals', takes: 'audio', makes: 'audio' },
  enhance: { label: 'Clean up speech', takes: 'audio', makes: 'audio' },
  transcribe: { label: 'Transcribe', takes: 'audio', makes: 'transcript' },
  subtitles: { label: 'Subtitles', takes: 'transcript', makes: 'nothing' },
  'watermark-check': { label: 'Check watermark', takes: 'audio', makes: 'nothing' },
  export: { label: 'Export', takes: 'audio', makes: 'nothing' },
};

/** The first step that cannot take what the step before it made, as a sentence; empty when the chain works. */
export function chainProblem(steps: RecipeStep[]): string {
  let holding: 'audio' | 'transcript' | 'nothing' = 'audio';
  for (const [index, step] of steps.entries()) {
    const tool = STEP_TOOLS[step.tool];
    if (!tool) return `Step ${index + 1} uses an unknown tool.`;
    if (tool.takes !== holding) {
      return holding === 'nothing'
        ? `Step ${index + 1} (${tool.label}) has nothing to work on: the step before it makes no audio.`
        : `Step ${index + 1} (${tool.label}) needs ${tool.takes}, but the step before it makes a ${holding}.`;
    }
    holding = tool.makes;
  }
  return '';
}

function assetTitle(asset: Asset): string {
  const title = asset.metadata?.title;
  return typeof title === 'string' && title.trim() ? title : asset.file_name || asset.id;
}

function StepSettings({ step, onChange }: { step: RecipeStep; onChange: (settings: Record<string, unknown>) => void }) {
  const settings = step.settings ?? {};
  if (step.tool === 'isolate') {
    return (
      <select aria-label="Separation model" value={String(settings.model ?? 'roformer')} onChange={(event) => onChange({ ...settings, model: event.currentTarget.value })}>
        <option value="roformer">Mel-Band RoFormer</option>
        <option value="demucs">Demucs</option>
      </select>
    );
  }
  if (step.tool === 'transcribe') {
    return (
      <label className="voice-batch-inline">Speakers
        <select aria-label="Speakers" value={String(settings.speakers ?? 0)} onChange={(event) => onChange({ ...settings, speakers: Number(event.currentTarget.value) })}>
          <option value="0">Automatic</option>
          {[1, 2, 3, 4, 5, 6, 7, 8].map((count) => <option key={count} value={count}>{count}</option>)}
        </select>
      </label>
    );
  }
  if (step.tool === 'subtitles') {
    const formats = Array.isArray(settings.formats) ? (settings.formats as string[]) : ['srt', 'vtt'];
    return (
      <span className="voice-batch-inline">
        {['srt', 'vtt', 'txt'].map((format) => (
          <label key={format}>
            <input type="checkbox" checked={formats.includes(format)} onChange={(event) => onChange({
              ...settings, formats: event.currentTarget.checked ? [...formats, format] : formats.filter((entry) => entry !== format),
            })} />{format.toUpperCase()}
          </label>
        ))}
      </span>
    );
  }
  if (step.tool === 'export') {
    return (
      <select aria-label="Export format" value={String(settings.format ?? 'mp3')} onChange={(event) => onChange({ ...settings, format: event.currentTarget.value })}>
        {['mp3', 'opus', 'flac', 'wav16', 'wav24'].map((format) => <option key={format} value={format}>{format.toUpperCase()}</option>)}
      </select>
    );
  }
  return null;
}

function RecipeEditor({ recipe, onSaved, onCancel }: { recipe: Recipe | null; onSaved: (recipe: Recipe) => void; onCancel: () => void }) {
  const [name, setName] = useState(recipe?.name ?? '');
  const [steps, setSteps] = useState<RecipeStep[]>(recipe?.steps ?? [{ tool: 'isolate', settings: {} }]);
  const save = useMutation({ mutationFn: () => voiceApiClient.saveRecipe({ name, steps }, recipe?.id), onSuccess: onSaved });
  const problem = chainProblem(steps);
  const update = (index: number, next: RecipeStep) => setSteps((current) => current.map((step, at) => (at === index ? next : step)));
  return (
    <form className="voice-batch-editor" aria-label={recipe ? `Edit ${recipe.name}` : 'New recipe'} onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
      <label>Recipe name<input value={name} maxLength={120} onChange={(event) => setName(event.currentTarget.value)} placeholder="Clean and subtitle" /></label>
      <ol className="voice-batch-steps">
        {steps.map((step, index) => (
          <li key={index}>
            <select aria-label={`Step ${index + 1} tool`} value={step.tool} onChange={(event) => update(index, { tool: event.currentTarget.value, settings: {} })}>
              {Object.entries(STEP_TOOLS).map(([id, tool]) => <option key={id} value={id}>{tool.label}</option>)}
            </select>
            <StepSettings step={step} onChange={(settings) => update(index, { ...step, settings })} />
            <Button size="compact-xs" variant="subtle" aria-label={`Remove step ${index + 1}`} disabled={steps.length === 1} onClick={() => setSteps((current) => current.filter((_, at) => at !== index))}>Remove</Button>
          </li>
        ))}
      </ol>
      <div className="voice-batch-actions">
        <Button size="xs" variant="light" disabled={steps.length >= 12} onClick={() => setSteps((current) => [...current, { tool: 'transcribe', settings: {} }])}>Add step</Button>
        <Button size="xs" type="submit" disabled={!name.trim() || Boolean(problem)} loading={save.isPending}>Save recipe</Button>
        <Button size="xs" variant="subtle" onClick={onCancel}>Cancel</Button>
      </div>
      {problem ? <Text size="xs" role="alert">{problem}</Text> : null}
      {save.isError ? <Text size="xs" role="alert">{save.error instanceof Error ? save.error.message : 'The recipe could not be saved.'}</Text> : null}
    </form>
  );
}

function progress(run: BatchRun): { finished: number; total: number } {
  const counts = run.counts ?? {};
  const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
  const finished = (counts.done ?? 0) + (counts.skipped ?? 0) + (counts.failed ?? 0);
  return { finished, total };
}

function RunDetail({ runId }: { runId: string }) {
  const queryClient = useQueryClient();
  const run = useQuery({
    queryKey: [...BATCHES_KEY, runId],
    queryFn: () => voiceApiClient.getBatch(runId),
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 3000 : false),
  });
  const cancel = useMutation({
    mutationFn: () => voiceApiClient.cancelBatch(runId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: BATCHES_KEY }),
  });
  if (!run.data) return <Text size="sm">Loading the run…</Text>;
  const { finished, total } = progress(run.data);
  return (
    <div className="voice-batch-run" aria-label={`Run ${run.data.title}`}>
      <div className="voice-section-head">
        <div><h4>{run.data.title}</h4><Text size="xs">Recipe version {run.data.recipe_version}{run.data.watch_folder ? ` · watch folder ${run.data.watch_folder}` : ''}</Text></div>
        {run.data.status === 'running' ? <Button size="xs" variant="light" color="red" loading={cancel.isPending} onClick={() => cancel.mutate()}>Cancel run</Button> : null}
      </div>
      <progress max={Math.max(1, total)} value={finished} aria-label="Batch progress" />
      <Text size="xs" role="status">{finished} of {total} finished · {run.data.status}</Text>
      <table className="voice-batch-items">
        <thead><tr><th scope="col">#</th><th scope="col">Input</th><th scope="col">Step</th><th scope="col">Status</th><th scope="col">Outputs</th></tr></thead>
        <tbody>
          {(run.data.items ?? []).map((item) => (
            <tr key={item.id}>
              <td>{item.position + 1}</td>
              <td>{item.output_name || item.source_asset_id}</td>
              <td>{Math.min(item.step_index + 1, (run.data.steps ?? []).length)} / {(run.data.steps ?? []).length}</td>
              <td>{item.status}{item.attempts ? ` (retry ${item.attempts})` : ''}{item.error ? <small> {item.error}</small> : null}</td>
              <td>{item.outputs.map((output, index) => <span key={index} className="voice-batch-output">{String(output.title ?? output.kind ?? output.tool ?? 'output')}</span>)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const CAPABILITY_LABELS: Record<string, string> = {
  'voice.speak': 'Speak with library voices',
  'voice.transcribe': 'Transcribe recordings',
  'voice.list_voices': 'List library voices',
  'voice.design': 'Design voices',
  'voice.isolate': 'Isolate vocals',
  'dub.status': 'Read dubbing status',
};

function ApiClients() {
  const queryClient = useQueryClient();
  const clients = useQuery({ queryKey: CLIENTS_KEY, queryFn: () => voiceApiClient.listClients(), retry: false });
  const [name, setName] = useState('');
  const [granted, setGranted] = useState<string[]>(['voice.speak', 'voice.list_voices']);
  const [issued, setIssued] = useState<ClientCredential | null>(null);
  const issue = useMutation({
    mutationFn: () => voiceApiClient.issueClient(name.trim(), granted, 90),
    onSuccess: (credential) => { setIssued(credential); setName(''); void queryClient.invalidateQueries({ queryKey: CLIENTS_KEY }); },
  });
  const revoke = useMutation({
    mutationFn: (clientId: string) => voiceApiClient.revokeClient(clientId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: CLIENTS_KEY }),
  });
  if (clients.isError) return <Text size="xs">API clients are managed by workspace admins.</Text>;
  return (
    <div className="voice-batch-clients">
      <Text size="xs">Scripts and MCP clients call <code>/api/voice/v1</code> or <code>/mcp/voice</code> with <code>Authorization: Bearer</code> and an <code>X-Omnix-Client</code> header. A client can do only what it is granted, in this workspace.</Text>
      {issued?.token ? (
        <div className="voice-notice" role="status">
          Token for {issued.name}, shown once: <code className="voice-batch-token">{issued.token}</code>
          <Button size="compact-xs" variant="subtle" onClick={() => void navigator.clipboard?.writeText(issued.token ?? '')}>Copy</Button>
        </div>
      ) : null}
      <form className="voice-batch-editor" aria-label="New API client" onSubmit={(event) => { event.preventDefault(); issue.mutate(); }}>
        <label>Client name<input value={name} maxLength={120} onChange={(event) => setName(event.currentTarget.value)} placeholder="Claude Desktop" /></label>
        <fieldset><legend>Allowed</legend>
          {(clients.data?.capabilities ?? Object.keys(CAPABILITY_LABELS)).map((capability) => (
            <label key={capability}>
              <input type="checkbox" checked={granted.includes(capability)} onChange={(event) => {
                const { checked } = event.currentTarget;
                setGranted((current) => (checked ? [...current, capability] : current.filter((entry) => entry !== capability)));
              }} />
              {CAPABILITY_LABELS[capability] ?? capability}
            </label>
          ))}
        </fieldset>
        <Button size="xs" type="submit" disabled={!name.trim() || !granted.length} loading={issue.isPending}>Issue token (90 days)</Button>
        {issue.isError ? <Text size="xs" role="alert">{issue.error instanceof Error ? issue.error.message : 'The client could not be added.'}</Text> : null}
      </form>
      <ul className="voice-batch-list" aria-label="API clients">
        {(clients.data?.clients ?? []).map((client) => (
          <li key={client.id}>
            <b>{client.name}</b>
            <small>{client.capabilities.map((capability) => CAPABILITY_LABELS[capability] ?? capability).join(', ')}</small>
            <small>{client.revoked_at ? 'Revoked' : client.last_used_at ? `Last used ${new Date(client.last_used_at).toLocaleString()}` : 'Not used yet'}</small>
            {client.revoked_at ? null : <Button size="compact-xs" variant="subtle" color="red" onClick={() => revoke.mutate(client.id)}>Revoke</Button>}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Batch: recipes of tool steps, runs over many recordings, watch-folder runs, and API clients. */
export function BatchTool({ assets }: { assets: Asset[] }) {
  const queryClient = useQueryClient();
  const recipes = useQuery({ queryKey: RECIPES_KEY, queryFn: () => voiceApiClient.listRecipes() });
  const runs = useQuery({
    queryKey: BATCHES_KEY,
    queryFn: () => voiceApiClient.listBatches(),
    refetchInterval: (query) => (query.state.data?.runs.some((run) => run.status === 'running') ? 5000 : false),
  });
  const sources = useMemo(() => assets.filter((asset) => SOURCE_TYPES.has(asset.type) && asset.mime_type.startsWith('audio/')), [assets]);
  const [editing, setEditing] = useState<Recipe | 'new' | null>(null);
  const [recipeId, setRecipeId] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [openRun, setOpenRun] = useState('');
  const start = useMutation({
    mutationFn: () => voiceApiClient.startBatch(recipeId, selected),
    onSuccess: (run) => { setOpenRun(run.id); setSelected([]); void queryClient.invalidateQueries({ queryKey: BATCHES_KEY }); },
  });
  const remove = useMutation({
    mutationFn: (id: string) => voiceApiClient.deleteRecipe(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: RECIPES_KEY }),
  });
  const recipeList = recipes.data?.recipes ?? [];

  return (
    <section className="voice-batch" aria-label="Batch">
      <div className="voice-section-head">
        <div><h3>Batch</h3><Text size="sm">Save a chain of tools as a recipe, then run it over many recordings. Each recording moves through the steps on its own; a failed step is retried once.</Text></div>
      </div>

      <div className="voice-batch-columns">
        <div aria-label="Recipes">
          <div className="voice-section-head"><h4>Recipes</h4><Button size="xs" variant="light" onClick={() => setEditing('new')}>New recipe</Button></div>
          {editing ? (
            <RecipeEditor
              key={editing === 'new' ? 'new' : editing.id}
              recipe={editing === 'new' ? null : editing}
              onCancel={() => setEditing(null)}
              onSaved={(saved) => { setEditing(null); setRecipeId(saved.id); void queryClient.invalidateQueries({ queryKey: RECIPES_KEY }); }}
            />
          ) : null}
          {recipeList.length ? (
            <ul className="voice-batch-list">
              {recipeList.map((recipe) => (
                <li key={recipe.id}>
                  <b>{recipe.name}</b>
                  <small>{recipe.steps.map((step) => STEP_TOOLS[step.tool]?.label ?? step.tool).join(' → ')} · v{recipe.version}</small>
                  <span>
                    <Button size="compact-xs" variant="subtle" onClick={() => setEditing(recipe)}>Edit</Button>
                    <Button size="compact-xs" variant="subtle" color="red" onClick={() => remove.mutate(recipe.id)}>Delete</Button>
                  </span>
                </li>
              ))}
            </ul>
          ) : <Text size="xs">No recipes yet. Isolate → Clean up → Transcribe → Subtitles is a good first one.</Text>}
        </div>

        <div aria-label="Start a batch">
          <h4>Run a batch</h4>
          <label>Recipe<select aria-label="Batch recipe" value={recipeId} onChange={(event) => setRecipeId(event.currentTarget.value)}>
            <option value="">Choose a recipe</option>
            {recipeList.map((recipe) => <option key={recipe.id} value={recipe.id}>{recipe.name}</option>)}
          </select></label>
          <fieldset className="voice-batch-sources"><legend>Recordings ({selected.length} chosen)</legend>
            {sources.length ? sources.map((asset) => (
              <label key={asset.id}>
                <input type="checkbox" checked={selected.includes(asset.id)} onChange={(event) => {
                  const { checked } = event.currentTarget;
                  setSelected((current) => (checked ? [...current, asset.id] : current.filter((entry) => entry !== asset.id)));
                }} />
                {assetTitle(asset)}
              </label>
            )) : <Text size="xs">No stored recordings yet.</Text>}
          </fieldset>
          <div className="voice-batch-actions">
            <Button size="xs" variant="subtle" disabled={!sources.length} onClick={() => setSelected(sources.map((asset) => asset.id))}>Choose all</Button>
            <Button size="xs" disabled={!recipeId || !selected.length} loading={start.isPending} onClick={() => start.mutate()}>Start batch</Button>
          </div>
          {start.isError ? <Text size="xs" role="alert">{start.error instanceof Error ? start.error.message : 'The batch could not start.'}</Text> : null}
          <Text size="xs">Watch folders run a recipe on every new file in a folder the operator configures (<code>OMNIX_VOICE_WATCH_FOLDERS</code>); their runs appear below.</Text>
        </div>
      </div>

      <h4>Runs</h4>
      {(runs.data?.runs ?? []).length ? (
        <ul className="voice-batch-list" aria-label="Batch runs">
          {(runs.data?.runs ?? []).map((run) => (
            <li key={run.id}>
              <button type="button" className="voice-batch-run-button" aria-expanded={openRun === run.id} onClick={() => setOpenRun(openRun === run.id ? '' : run.id)}>
                <b>{run.title}</b>
              </button>
              <small>{run.status} · {new Date(run.created_at).toLocaleString()}{run.watch_folder ? ' · watch folder' : ''}</small>
            </li>
          ))}
        </ul>
      ) : <Text size="xs">No runs yet.</Text>}
      {openRun ? <RunDetail runId={openRun} /> : null}

      <details className="voice-inspector-section">
        <summary>API clients and MCP</summary>
        <ApiClients />
      </details>
    </section>
  );
}
