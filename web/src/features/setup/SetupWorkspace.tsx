import { Button, Text } from '@mantine/core';
import { useNavigate } from '@tanstack/react-router';
import type { OmnixModuleDefinition } from '../../app/modules';
import { ModelPacksPanel } from './ModelPacksPanel';
import './setup.css';

/**
 * The setup screen the desktop app opens on its first start (desktop roadmap §4.5). On the very first run the owner
 * secures their account first (email and password, in Settings); then picks the AI models this computer can run.
 * Nothing large downloads without that choice, and everything stays available later from Settings, Models.
 */
export function SetupWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const navigate = useNavigate();
  const firstRun = typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('first_run') === '1';
  return (
    <main className="setup-workspace" aria-labelledby="setup-title">
      <header>
        <h1 id="setup-title">{module.label}</h1>
        <Text size="sm">Omnix runs chat right away. Voice, transcription and images need AI models on this computer: choose what to download.</Text>
      </header>
      {firstRun ? (
        <section className="setup-step" aria-label="Secure your account">
          <b>First, secure this computer's owner account</b>
          <Text size="sm">Add your email and a password, so only you can sign in to Omnix on this computer.</Text>
          <div><Button component="a" href="/settings?category=overview" size="xs" variant="light">Set your email and password</Button></div>
        </section>
      ) : null}
      <ModelPacksPanel mode="setup" />
      <div className="setup-footer">
        <span />
        <Button variant="subtle" onClick={() => { void navigate({ to: '/chatbot' }); }}>Continue to Omnix</Button>
      </div>
    </main>
  );
}
