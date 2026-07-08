from pathlib import Path

client = Path("apps/web/src/features/chatbot/memoryClient.ts")
text = client.read_text(encoding="utf-8")
marker = "export interface SessionMemoryState {\n"
settings_types = """export interface AssistantMemoryRuntimeSettings {
  curated_memory_enabled: boolean;
  suggestions_enabled: boolean;
  history_recall_enabled: boolean;
  compaction_enabled: boolean;
  hermes_sync_enabled: boolean;
  require_approval_for_inferred_memory: boolean;
  memory_token_budget: number;
  history_token_budget: number;
  retention_days: number;
  show_memory_use_indicator: boolean;
}

export interface AssistantMemoryRuntimeStatus {
  settings: AssistantMemoryRuntimeSettings;
  settings_path: string;
  environment_overrides: string[];
  approval_policy_locked: boolean;
  diagnostics_policy: 'content_free';
}

"""
if text.count(marker) != 1:
    raise SystemExit("memory client settings type marker missing")
text = text.replace(marker, settings_types + marker, 1)
old = """  refresh(sessionId: string, expectedRevision?: number | null): Promise<SessionMemoryState> {
    return request(`/api/chat/sessions/${encodeURIComponent(sessionId)}/memory/refresh`, jsonInit('POST', {
      expected_snapshot_revision: expectedRevision ?? null,
      token_budget: 4000,
    }));
  },
};
"""
new = """  refresh(sessionId: string, expectedRevision?: number | null): Promise<SessionMemoryState> {
    return request(`/api/chat/sessions/${encodeURIComponent(sessionId)}/memory/refresh`, jsonInit('POST', {
      expected_snapshot_revision: expectedRevision ?? null,
      token_budget: 4000,
    }));
  },
  settings(): Promise<AssistantMemoryRuntimeStatus> {
    return request('/api/assistant/memory/settings');
  },
  updateSettings(update: Partial<AssistantMemoryRuntimeSettings>): Promise<AssistantMemoryRuntimeStatus> {
    return request('/api/assistant/memory/settings', jsonInit('POST', update));
  },
};
"""
if text.count(old) != 1:
    raise SystemExit("memory client method marker missing")
client.write_text(text.replace(old, new, 1), encoding="utf-8")

panel = Path("apps/web/src/features/chatbot/MemoryManagementPanel.tsx")
text = panel.read_text(encoding="utf-8")
old = """  const snapshotQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'memory-state', sessionId],
    queryFn: () => memoryClient.sessionState(sessionId ?? ''),
    enabled: Boolean(sessionId),
  });
"""
new = old + """  const settingsQuery = useQuery({
    queryKey: ['feature', 'chatbot', 'memory-settings'],
    queryFn: () => memoryClient.settings(),
  });
"""
if text.count(old) != 1:
    raise SystemExit("panel settings query marker missing")
text = text.replace(old, new, 1)
old = """      queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'sessions'] }),
    ]);
"""
new = """      queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'sessions'] }),
      queryClient.invalidateQueries({ queryKey: ['feature', 'chatbot', 'memory-settings'] }),
    ]);
"""
if text.count(old) != 1:
    raise SystemExit("panel invalidation marker missing")
text = text.replace(old, new, 1)
old = """  const refreshMutation = useMutation({
    mutationFn: () => memoryClient.refresh(sessionId ?? '', snapshotQuery.data?.snapshot_revision),
    onSuccess: async () => {
      setStatus('Active chat memory refreshed.');
      await refreshAll();
    },
    onError: (error) => setStatus(error instanceof Error ? error.message : 'Memory refresh failed.'),
  });
"""
new = old + """  const settingsMutation = useMutation({
    mutationFn: (update: Parameters<typeof memoryClient.updateSettings>[0]) => memoryClient.updateSettings(update),
    onSuccess: async () => {
      setStatus('Memory settings saved. New server-side behavior is active immediately.');
      await refreshAll();
    },
    onError: (error) => setStatus(error instanceof Error ? error.message : 'Memory settings update failed.'),
  });
"""
if text.count(old) != 1:
    raise SystemExit("panel settings mutation marker missing")
text = text.replace(old, new, 1)
old = """        <article>
          <h3>Add explicit memory</h3>
          <label>Scope<select aria-label=\"New memory scope\" value={newScope} onChange={(event) => setNewScope(event.currentTarget.value as MemoryScope)}>{scopes.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
          <label>Category<select aria-label=\"New memory category\" value={newCategory} onChange={(event) => setNewCategory(event.currentTarget.value as MemoryCategory)}>{categories.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
          <label>Memory<textarea aria-label=\"New memory content\" rows={3} value={newContent} onChange={(event) => setNewContent(event.currentTarget.value)} /></label>
          <button type=\"button\" disabled={!newContent.trim() || createMutation.isPending} onClick={() => createMutation.mutate()}>Save memory</button>
        </article>
"""
settings_article = old + """        <article>
          <h3>Memory and privacy settings</h3>
          {settingsQuery.isPending ? <p>Loading settings…</p> : settingsQuery.data ? (
            <>
              {([
                ['curated_memory_enabled', 'Use approved memory in Chat'],
                ['suggestions_enabled', 'Create pending suggestions'],
                ['history_recall_enabled', 'Search previous conversations'],
                ['compaction_enabled', 'Compact long conversations'],
                ['hermes_sync_enabled', 'Allow Hermes synchronization'],
                ['show_memory_use_indicator', 'Show memory-use indicators'],
              ] as const).map(([key, label]) => (
                <label key={key}>
                  <input
                    type=\"checkbox\"
                    checked={settingsQuery.data.settings[key]}
                    disabled={settingsMutation.isPending || settingsQuery.data.environment_overrides.includes(key)}
                    onChange={(event) => settingsMutation.mutate({ [key]: event.currentTarget.checked })}
                  />
                  {label}
                  {settingsQuery.data.environment_overrides.includes(key) ? ' · environment controlled' : ''}
                </label>
              ))}
              <p>Inferred memory approval is required and cannot be disabled. Diagnostics are content-free.</p>
            </>
          ) : <p>Memory settings are unavailable.</p>}
        </article>
"""
if text.count(old) != 1:
    raise SystemExit("panel settings article marker missing")
text = text.replace(old, settings_article, 1)
panel.write_text(text, encoding="utf-8")
