import type { OmnixModuleDefinition } from '../app/modules';

const moduleCapabilities: Record<string, string[]> = {
  rpg: ['Turn contracts', 'Deterministic state', 'Journal', 'Party', 'Combat', 'Autoplay reports'],
  chatbot: ['Shared provider selector', 'Streaming transcript', 'Conversation history', 'Prompt diagnostics'],
  storyteller: ['Story jobs', 'Outlines', 'Branches', 'Exports'],
  podcast: ['Script planning', 'Speaker assignment', 'TTS jobs', 'Audio exports'],
  voice: ['TTS generation', 'Audio previews', 'Provider status', 'Playback controls'],
  'voice-cloning': ['Sample ingestion', 'Voice profiles', 'Preview generation', 'Training jobs'],
  stt: ['Audio ingestion', 'Transcription jobs', 'Transcript assets', 'Alignment'],
  'image-generation': ['Prompting', 'Image jobs', 'Asset gallery', 'Provider diagnostics'],
  providers: ['Provider registry', 'Model discovery', 'Health checks', 'Capabilities'],
  models: ['Installed models', 'Remote models', 'Capability mapping', 'Resource hints'],
  jobs: ['Run queue', 'Progress events', 'Logs', 'History'],
  assets: ['Audio', 'Images', 'Transcripts', 'Reports', 'Checkpoints'],
  reports: ['Run reports', 'RPG autoplay evidence', 'Diagnostics exports', 'Generated documents'],
  settings: ['Global settings', 'Provider settings', 'Model settings', 'Local services'],
  diagnostics: ['Health checks', 'Event stream', 'Logs', 'Troubleshooting'],
};

export function ModuleWorkspace({ module }: { module: OmnixModuleDefinition }) {
  const capabilities = moduleCapabilities[module.id] ?? [];

  return (
    <section className="workspace-card" aria-labelledby="module-title">
      <div className="workspace-heading">
        <div>
          <p className="eyebrow">Module workspace</p>
          <h3 id="module-title">{module.label}</h3>
        </div>
        <code>{module.route}</code>
      </div>

      <p className="workspace-summary">{module.summary}</p>

      <div className="workspace-grid">
        <article>
          <h4>Infrastructure contract</h4>
          <ul>
            <li>Uses the shared app shell.</li>
            <li>Uses the shared typed API client.</li>
            <li>Uses the shared event client for streaming/progress.</li>
            <li>Uses shared jobs, assets, providers, diagnostics, and design primitives.</li>
          </ul>
        </article>

        <article>
          <h4>Module capabilities</h4>
          <ul>
            {capabilities.map((capability) => (
              <li key={capability}>{capability}</li>
            ))}
          </ul>
        </article>
      </div>
    </section>
  );
}
