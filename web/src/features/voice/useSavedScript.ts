import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { voiceApiClient, type VoiceScript, type VoiceScriptWrite } from './api/voiceClient';

export const SCRIPTS_QUERY_KEY = ['voice', 'scripts'] as const;

/**
 * Saved scripts (Phase 1): lines keep their identity across edits, so one line can be rendered
 * again and every take is kept. Saving needs PostgreSQL; without it the library stays hidden.
 */
export function useSavedScript({ scriptText, setScriptText, buildWrite }: {
  scriptText: string;
  setScriptText: (text: string) => void;
  buildWrite: () => Omit<VoiceScriptWrite, 'expected_revision'>;
}) {
  const queryClient = useQueryClient();
  const [openScript, setOpenScript] = useState<VoiceScript | null>(null);
  const scriptsQuery = useQuery({ queryKey: SCRIPTS_QUERY_KEY, queryFn: () => voiceApiClient.listScripts(), retry: false });
  const dirty = Boolean(openScript && openScript.text !== scriptText);

  const refresh = () => queryClient.invalidateQueries({ queryKey: SCRIPTS_QUERY_KEY });

  const saveMutation = useMutation({
    mutationFn: async (asNew: boolean): Promise<VoiceScript> => {
      const write = buildWrite();
      if (openScript && !asNew) {
        return voiceApiClient.updateScript(openScript.id, { ...write, expected_revision: openScript.revision });
      }
      return voiceApiClient.createScript(write);
    },
    onSuccess: async (script) => {
      setOpenScript(script);
      await refresh();
    },
  });

  const openMutation = useMutation({
    mutationFn: (scriptId: string) => voiceApiClient.getScript(scriptId),
    onSuccess: (script) => {
      setOpenScript(script);
      setScriptText(script.text);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (scriptId: string) => voiceApiClient.deleteScript(scriptId),
    onSuccess: async () => {
      setOpenScript(null);
      await refresh();
    },
  });

  /** The open script as saved, saving pending edits first; ``null`` when no script is open. */
  async function ensureSaved(): Promise<VoiceScript | null> {
    if (!openScript) return null;
    if (!dirty) return openScript;
    return saveMutation.mutateAsync(false);
  }

  /** Reload the open script (after a render added takes). */
  async function reload(): Promise<void> {
    if (!openScript) return;
    setOpenScript(await voiceApiClient.getScript(openScript.id));
  }

  return {
    available: !scriptsQuery.isError,
    scripts: scriptsQuery.data?.scripts ?? [],
    openScript,
    setOpenScript,
    dirty,
    save: (asNew = false) => saveMutation.mutateAsync(asNew),
    saving: saveMutation.isPending,
    saveError: saveMutation.error,
    open: (scriptId: string) => openMutation.mutate(scriptId),
    close: () => setOpenScript(null),
    remove: () => openScript && deleteMutation.mutate(openScript.id),
    ensureSaved,
    reload,
  };
}
