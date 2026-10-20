import { Button, Text, Title } from '@mantine/core';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import type { OmnixModuleDefinition } from '../../app/modules';
import { WorkspacePanel } from '../../design/primitives';
import { dubbingClient, type DubProject } from './api/dubbingClient';
import { DubProjectView } from './DubProjectView';
import { DUB_LANGUAGES, TRANSLATORS } from './dubbingOptions';
import './DubbingWorkspace.css';

export const PROJECTS_KEY = ['feature', 'dubbing', 'projects'] as const;

function NewDubForm({ onCreated }: { onCreated: (project: DubProject) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [source, setSource] = useState('en');
  const [target, setTarget] = useState('es');
  const [speakers, setSpeakers] = useState(0);
  const [translator, setTranslator] = useState('');
  const create = useMutation({
    mutationFn: () => dubbingClient.createProject({ file: file as File, title, sourceLanguage: source, targetLanguage: target, speakers, translator }),
    onSuccess: async (project) => {
      await dubbingClient.runStep(project.id, 'ingest', { chain: true });
      onCreated(project);
    },
  });
  const cloud = TRANSLATORS.find((entry) => entry.id === translator)?.cloud;
  return (
    <form className="dub-new" aria-label="New dub" onSubmit={(event) => { event.preventDefault(); if (file) create.mutate(); }}>
      <h3>New dub</h3>
      <label>Video<input aria-label="Video" type="file" accept="video/mp4,video/quicktime,video/x-matroska,video/webm,.mkv" onChange={(event) => setFile(event.currentTarget.files?.[0] ?? null)} /></label>
      <label>Title<input aria-label="Title" value={title} placeholder={file?.name.replace(/\.[^.]+$/, '') ?? 'From the file name'} onChange={(event) => setTitle(event.currentTarget.value)} /></label>
      <div className="dub-row">
        <label>From<select aria-label="Source language" value={source} onChange={(event) => setSource(event.currentTarget.value)}>{DUB_LANGUAGES.map((entry) => <option key={entry.code} value={entry.code}>{entry.label}</option>)}</select></label>
        <label>To<select aria-label="Target language" value={target} onChange={(event) => setTarget(event.currentTarget.value)}>{DUB_LANGUAGES.map((entry) => <option key={entry.code} value={entry.code}>{entry.label}</option>)}</select></label>
        <label>Speakers<select aria-label="Speakers" value={speakers} onChange={(event) => setSpeakers(Number(event.currentTarget.value))}>{[0, 1, 2, 3, 4, 5, 6, 7, 8].map((count) => <option key={count} value={count}>{count === 0 ? 'Automatic' : count}</option>)}</select></label>
      </div>
      <label>Translator<select aria-label="Translator" value={translator} onChange={(event) => setTranslator(event.currentTarget.value)}>{TRANSLATORS.map((entry) => <option key={entry.id} value={entry.id}>{entry.label}</option>)}</select></label>
      {cloud ? <Text size="xs" className="dub-warning" role="note">The transcript leaves this machine: a cloud model translates it.</Text> : null}
      <Button type="submit" disabled={!file || source === target} loading={create.isPending}>Upload and start</Button>
      {create.isError ? <Text size="xs" role="alert">{create.error instanceof Error ? create.error.message : 'The dub could not be started.'}</Text> : null}
    </form>
  );
}

const DUBBING_SUMMARY = 'Translate and re-voice a video. Every line is reviewed and approved before the final mix.';

/** Dubbing: translate and re-voice a video, with a person approving every line before the mix. */
export function DubbingWorkspace({ module }: { module: OmnixModuleDefinition }) {
  return (
    <WorkspacePanel label={module.label}>
      <DubbingApp heading={<div><Title order={2}>{module.label}</Title><Text size="sm">{DUBBING_SUMMARY}</Text></div>} />
    </WorkspacePanel>
  );
}

/** Dubbing as a Voice Studio tool: the same app inside the studio's canvas, beside its tool rail. */
export function DubbingTool() {
  return (
    <section className="voice-dub" aria-label="Dub">
      <DubbingApp heading={<div><h3>Dub</h3><Text size="sm">{DUBBING_SUMMARY}</Text></div>} />
    </section>
  );
}

function DubbingApp({ heading }: { heading: ReactNode }) {
  const queryClient = useQueryClient();
  const [openId, setOpenId] = useState('');
  const projects = useQuery({ queryKey: PROJECTS_KEY, queryFn: () => dubbingClient.listProjects() });
  return (
    <div className="dub-app">
      <header className="dub-header">{heading}</header>
      <div className="dub-body">
        <aside className="dub-sidebar">
          <NewDubForm onCreated={(project) => { void queryClient.invalidateQueries({ queryKey: PROJECTS_KEY }); setOpenId(project.id); }} />
          <nav aria-label="Dubbing projects" className="dub-projects">
            {(projects.data ?? []).map((project) => (
              <button key={project.id} type="button" className={project.id === openId ? 'active' : ''} aria-current={project.id === openId ? 'page' : undefined} onClick={() => setOpenId(project.id)}>
                <b>{project.title}</b><small>{project.source_language} → {project.target_language}</small>
              </button>
            ))}
            {projects.data && !projects.data.length ? <Text size="xs">No dubs yet.</Text> : null}
          </nav>
        </aside>
        {/* A section, not <main>: inside Voice Studio the canvas is already the page's main region. */}
        <section className="dub-main" aria-label="Dub project">
          {openId ? <DubProjectView key={openId} projectId={openId} onDeleted={() => { setOpenId(''); void queryClient.invalidateQueries({ queryKey: PROJECTS_KEY }); }} /> : <Text size="sm">Upload a video, or open a dub from the list.</Text>}
        </section>
      </div>
    </div>
  );
}
