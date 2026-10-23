import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { RpgWorldSummary } from './api/rpgWorldLibraryClient';
import { rpgWorldSharingClient, type RpgGitHubDeviceSignIn } from './api/rpgWorldSharingClient';

const TOKEN_URL = 'https://github.com/settings/tokens/new?scopes=public_repo&description=Omnix%20world%20sharing';
const STATUS_KEY = ['feature', 'rpg', 'world-sharing', 'github'];

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

/** GitHub sign-in for sharing: GitHub's device sign-in when Omnix has an OAuth app, or a pasted token. */
function GitHubSignIn({ deviceSignIn, repo }: { deviceSignIn: boolean; repo: string }) {
  const queryClient = useQueryClient();
  const [token, setToken] = useState('');
  const [device, setDevice] = useState<RpgGitHubDeviceSignIn | null>(null);
  const connected = async () => {
    setDevice(null);
    await queryClient.invalidateQueries({ queryKey: STATUS_KEY });
  };
  const connect = useMutation({ mutationFn: () => rpgWorldSharingClient.connectWithToken(token.trim()), onSuccess: connected });
  const start = useMutation({ mutationFn: () => rpgWorldSharingClient.startDeviceSignIn(), onSuccess: setDevice });
  const [pollError, setPollError] = useState('');

  useEffect(() => {
    if (!device) return undefined;
    const timer = window.setInterval(() => {
      rpgWorldSharingClient.pollDeviceSignIn(device.flow_id)
        .then((result) => (result.connected ? connected() : undefined))
        .catch((cause: unknown) => { setPollError(errorText(cause, 'GitHub sign-in did not finish.')); setDevice(null); });
    }, Math.max(5, device.interval) * 1000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- polls once per sign-in attempt
  }, [device]);

  return (
    <div className="rpg-share-sign-in">
      <p>Sharing opens a pull request on <strong>{repo}</strong> from your GitHub account. Its maintainers review it before anyone can download it.</p>
      {deviceSignIn ? (
        device ? (
          <p className="rpg-share-device">
            Enter <code>{device.user_code}</code> at <a href={device.verification_uri} rel="noreferrer" target="_blank">{device.verification_uri}</a>. This page carries on once GitHub confirms.
          </p>
        ) : (
          <button disabled={start.isPending} type="button" onClick={() => start.mutate()}>Sign in with GitHub</button>
        )
      ) : null}
      <label>
        <span>{deviceSignIn ? 'Or paste a GitHub token' : 'GitHub token'}</span>
        <input autoComplete="off" type="password" value={token} onChange={(event) => setToken(event.currentTarget.value)} />
      </label>
      <p className="rpg-share-help">
        <a href={TOKEN_URL} rel="noreferrer" target="_blank">Create a token</a> with the <code>public_repo</code> scope. Omnix keeps it in its secret store.
      </p>
      <button disabled={!token.trim() || connect.isPending} type="button" onClick={() => connect.mutate()}>
        {connect.isPending ? 'Connecting…' : 'Connect GitHub'}
      </button>
      {connect.isError || start.isError || pollError ? (
        <p className="rpg-authoring-feedback" role="alert">{pollError || errorText(connect.error ?? start.error, 'GitHub sign-in failed.')}</p>
      ) : null}
    </div>
  );
}

interface RpgWorldShareDialogProps {
  world: RpgWorldSummary;
  onClose: () => void;
}

export function RpgWorldShareDialog({ world, onClose }: RpgWorldShareDialogProps) {
  const queryClient = useQueryClient();
  const [summary, setSummary] = useState(world.description ?? '');
  const status = useQuery({ queryKey: STATUS_KEY, queryFn: () => rpgWorldSharingClient.gitHubStatus() });
  const share = useMutation({ mutationFn: () => rpgWorldSharingClient.share(world.id, summary.trim()) });
  const signOut = useMutation({
    mutationFn: () => rpgWorldSharingClient.disconnect(),
    onSuccess: async () => queryClient.invalidateQueries({ queryKey: STATUS_KEY }),
  });
  const github = status.data;
  return (
    <div className="rpg-authoring-modal" role="dialog" aria-modal="true" aria-label="Share to community">
      <form className="rpg-shared-world-dialog" onSubmit={(event) => { event.preventDefault(); share.mutate(); }}>
        <h3>Share {world.title}</h3>
        {status.isPending ? <p>Checking GitHub…</p> : null}
        {github && !github.connected ? <GitHubSignIn deviceSignIn={github.device_sign_in} repo={github.catalog_repo} /> : null}
        {github?.connected && !share.isSuccess ? (
          <>
            <p className="rpg-share-account">
              Signed in to GitHub as <strong>@{github.login}</strong>.{' '}
              <button className="rpg-link-button" type="button" onClick={() => signOut.mutate()}>Sign out</button>
            </p>
            <label>
              <span>Summary for the catalog</span>
              <textarea maxLength={2000} rows={4} value={summary} onChange={(event) => setSummary(event.currentTarget.value)} />
            </label>
            <p className="rpg-share-help">
              Omnix uploads this world&apos;s file (its lore, maps, openings and images) to a release on your fork of {github.catalog_repo}, then opens the pull request.
            </p>
          </>
        ) : null}
        {share.isSuccess ? (
          <p className="rpg-share-done" role="status">
            Pull request opened: <a href={share.data.pull_request_url} rel="noreferrer" target="_blank">{share.data.pull_request_url}</a>. The world is listed once it is reviewed and merged.
          </p>
        ) : null}
        {share.isError ? <p className="rpg-authoring-feedback" role="alert">{errorText(share.error, 'The world could not be shared.')}</p> : null}
        <div>
          <button className="rpg-secondary-button" type="button" onClick={onClose}>{share.isSuccess ? 'Done' : 'Cancel'}</button>
          {github?.connected && !share.isSuccess ? (
            <button disabled={share.isPending} type="submit">{share.isPending ? 'Sharing…' : 'Share to community'}</button>
          ) : null}
        </div>
      </form>
    </div>
  );
}
