import { Button, Checkbox, Text } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { AVATARS_QUERY_KEY, avatarsClient, type AvatarLibrary, type AvatarModel } from './api/modelPacksClient';

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function AvatarCard({ model, manage, accepted, busy, onInstall, onRemove }: {
  model: AvatarModel;
  manage: boolean;
  accepted: boolean;
  busy: boolean;
  onInstall: () => void;
  onRemove: () => void;
}) {
  return (
    <li className="setup-avatar" aria-label={model.name}>
      {model.preview_path ? <img className="setup-avatar-preview" src={model.preview_path} alt="" loading="lazy" /> : null}
      <div className="setup-avatar-body">
        <div className="setup-bundle-head">
          <b>{model.name}</b>
          {model.installed ? <span className="setup-chip setup-chip-installed">Downloaded</span> : null}
        </div>
        <Text size="xs" className="setup-muted">{model.description}</Text>
        <Text size="xs" className="setup-muted">
          <a href={model.model_license_url} target="_blank" rel="noreferrer">Model terms</a>
          {' · '}
          <a href={model.source_url} target="_blank" rel="noreferrer">Source</a>
        </Text>
        {manage ? (
          <div className="setup-bundle-actions">
            {model.installed
              ? <Button size="compact-xs" variant="subtle" color="red" loading={busy} onClick={onRemove}>Remove</Button>
              : <Button size="compact-xs" variant="light" loading={busy} disabled={!accepted} onClick={onInstall}>Download</Button>}
          </div>
        ) : null}
      </div>
    </li>
  );
}

/**
 * Live2D avatars to download (desktop roadmap §4.5), beside the AI models: a downloaded avatar can then be any
 * character's, chosen in Characters. The Live2D runtime downloads with the first avatar, from Live2D itself.
 */
export function AvatarPacksPanel() {
  const queryClient = useQueryClient();
  const libraryQuery = useQuery({ queryKey: AVATARS_QUERY_KEY, queryFn: () => avatarsClient.library(), retry: false });
  const [accepted, setAccepted] = useState(false);
  const [message, setMessage] = useState('');
  const settle = (library: AvatarLibrary) => {
    queryClient.setQueryData(AVATARS_QUERY_KEY, library);
    setMessage('');
  };
  const install = useMutation({ mutationFn: (modelId: string) => avatarsClient.install(modelId), onSuccess: settle,
    onError: (error) => setMessage(errorText(error)) });
  const remove = useMutation({ mutationFn: (modelId: string) => avatarsClient.remove(modelId), onSuccess: settle,
    onError: (error) => setMessage(errorText(error)) });

  if (libraryQuery.isError) return <div className="platform-empty" role="alert">{errorText(libraryQuery.error)}</div>;
  const library = libraryQuery.data;
  if (!library) return <div className="platform-empty" role="status">Loading the avatars…</div>;
  const runtimeLicence = library.models[0]?.runtime_license_url;
  const pending = install.isPending ? install.variables : remove.isPending ? remove.variables : null;

  return (
    <section className="setup-panel" aria-label="Live2D avatars">
      <header>
        <h2 className="setup-settings-title">Avatars</h2>
        <Text size="sm">Animated Live2D avatars for characters in chat and live voice. Download the ones you like, then choose one for a character in Characters.</Text>
      </header>
      {library.can_manage ? (
        <Checkbox
          checked={accepted}
          onChange={(event) => setAccepted(event.currentTarget.checked)}
          label={(
            <span>
              I accept the <a href={runtimeLicence} target="_blank" rel="noreferrer">Live2D Proprietary Software License</a> for
              the Live2D runtime, downloaded from Live2D with the first avatar, and each avatar's model terms.
            </span>
          )}
        />
      ) : (
        <div className="setup-message" role="status">The workspace owner or an admin downloads and removes avatars.</div>
      )}
      <ul className="setup-avatars">
        {library.models.map((model) => (
          <AvatarCard
            key={model.id}
            model={model}
            manage={library.can_manage}
            accepted={accepted}
            busy={pending === model.id}
            onInstall={() => install.mutate(model.id)}
            onRemove={() => { if (window.confirm(`Remove ${model.name}? It is deleted from this computer.`)) remove.mutate(model.id); }}
          />
        ))}
      </ul>
      {message ? <div className="setup-message" role="alert">{message}</div> : null}
    </section>
  );
}
