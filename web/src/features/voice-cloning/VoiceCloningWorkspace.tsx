import { Group, Progress, Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';
import { omnixApiClient } from '../../api/client';
import type { OmnixModuleDefinition } from '../../app/modules';
import { OmnixStatusPill, WorkspacePanel } from '../../design/primitives';
import { loadSettingsProfile, voiceStudioDefaults } from '../settings';
import { jobProgressPercent } from '../../api/jobProgress';
import { GatewayErrorNotice } from '../../shared/GatewayErrorNotice';
import { CloneVoicePanel, VoiceLibraryGrid, voiceAssetId, voiceAssetName, type VoiceAsset } from '../voice';

/**
 * The Voice Cloning sidebar module: the same clone panel and library as Voice Studio's
 * Voices tool, kept as its own entry (module id `voice-cloning`).
 */
export function VoiceCloningWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const queryClient = useQueryClient();
  const jobsQuery = useQuery({ queryKey: ['platform', 'jobs'], queryFn: () => omnixApiClient.listJobs() });
  const assetsQuery = useQuery({ queryKey: ['platform', 'assets'], queryFn: () => omnixApiClient.listAssets() });
  const settingsQuery = useQuery({ queryKey: ['settings', 'profile'], queryFn: () => loadSettingsProfile() });
  const defaults = useMemo(() => voiceStudioDefaults(settingsQuery.data?.profile), [settingsQuery.data?.profile]);
  const profileAssets = assetsQuery.data?.assets.filter((asset) => asset.type === 'voice_profile') ?? [];
  const voiceCloneJobs = jobsQuery.data?.jobs.filter((job) => job.module === 'voice-cloning') ?? [];
  const deleteMutation = useMutation({
    mutationFn: (asset: VoiceAsset) => omnixApiClient.deleteVoiceAsset(voiceAssetId(asset)),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] }); },
  });

  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['platform', 'jobs'] }),
      queryClient.invalidateQueries({ queryKey: ['platform', 'assets'] }),
    ]);
  }

  function requestDelete(asset: VoiceAsset) {
    if (typeof window !== 'undefined' && !window.confirm(`Delete “${voiceAssetName(asset)}”? This permanently removes the cloned voice audio and metadata.`)) return;
    deleteMutation.mutate(asset);
  }

  return (
    <WorkspacePanel>
      <div className="workspace-heading">
        <div>
          <p className="eyebrow">Feature module</p>
          <h2 id="module-title">{module.label}</h2>
        </div>
        <code>{module.route}</code>
      </div>
      <p className="workspace-summary">{module.summary}</p>
      <GatewayErrorNotice label="Voice cloning data" errors={[jobsQuery.error, assetsQuery.error]} />

      <div className="voice-voices voice-cloning-module">
        <CloneVoicePanel
          defaults={{
            revision: settingsQuery.data?.profile.revision ?? '',
            providerId: defaults.voiceCloningProviderId,
            language: defaults.cloningLanguage,
            quality: defaults.cloningQuality,
            sttProviderId: defaults.sttProviderId,
          }}
          onFinished={refresh}
        />
        <VoiceLibraryGrid
          assets={profileAssets}
          loading={assetsQuery.isLoading}
          failed={assetsQuery.isError}
          refreshing={assetsQuery.isFetching}
          onRefresh={() => void assetsQuery.refetch()}
          onDelete={requestDelete}
          deletingId={deleteMutation.isPending && deleteMutation.variables ? voiceAssetId(deleteMutation.variables) : ''}
          deleteFailed={deleteMutation.isError}
        />
      </div>

      <section className="feature-panel">
        <Title order={4}>Voice profile jobs</Title>
        {voiceCloneJobs.length ? (
          <div className="feature-list">
            {voiceCloneJobs.map((job) => (
              <article className="feature-mini-card" key={job.id}>
                <Group justify="space-between">
                  <strong>{job.type}</strong>
                  <OmnixStatusPill>{job.status}</OmnixStatusPill>
                </Group>
                <Progress value={jobProgressPercent(job.progress)} aria-label={`${job.type} progress`} />
                {job.status === 'failed' && typeof job.error?.message === 'string' ? <Text size="sm">{job.error.message}</Text> : null}
              </article>
            ))}
          </div>
        ) : (
          <div className="platform-empty" role="status">No voice profile jobs queued.</div>
        )}
      </section>
    </WorkspacePanel>
  );
}
