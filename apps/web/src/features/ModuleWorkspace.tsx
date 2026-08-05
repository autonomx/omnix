import type { OmnixModuleDefinition } from '../app/modules';
import { WorkspacePanel } from '../design/primitives';
import { ChatbotWorkspace } from './chatbot/ChatbotWorkspace';
import { ImageGenerationWorkspace } from './image-generation/ImageGenerationWorkspace';
import { PodcastWorkspace } from './podcast/PodcastWorkspace';
import { isPlatformModule, PlatformModuleWorkspace } from './platform/PlatformModuleWorkspace';
import { SettingsWorkspace } from './platform/SettingsWorkspace';
import { RpgWorkspace } from './rpg/RpgWorkspace';
import { SttWorkspace } from './stt/SttWorkspace';
import { StorytellerWorkspace } from './storyteller/StorytellerWorkspace';
import { TradingWorkspace } from './trading/TradingWorkspace';
import { VoiceCloningWorkspace } from './voice-cloning/VoiceCloningWorkspace';
import { VoiceWorkspace } from './voice/VoiceWorkspace';

const moduleCapabilities: Record<string, string[]> = {
  rpg: ['Turn contracts', 'Deterministic state', 'Journal', 'Party', 'Combat', 'Autoplay reports'],
  chatbot: ['Shared provider selector', 'Streaming transcript', 'Conversation history', 'Prompt diagnostics'],
  storyteller: ['Story jobs', 'Outlines', 'Branches', 'Exports'],
  podcast: ['Script planning', 'Speaker assignment', 'TTS jobs', 'Audio exports'],
  voice: ['TTS generation', 'Audio previews', 'Provider status', 'Playback controls'],
  'voice-cloning': ['Sample ingestion', 'Voice profiles', 'Preview generation', 'Training jobs'],
  stt: ['Audio ingestion', 'Transcription jobs', 'Transcript assets', 'Alignment'],
  'image-generation': ['Prompting', 'Image jobs', 'Asset gallery', 'Provider diagnostics'],
  trading: ['Multi-chart workspace', 'Canonical instruments', 'Drawings', 'Indicators', 'Provider provenance'],
  providers: ['Provider registry', 'Model discovery', 'Health checks', 'Capabilities'],
  models: ['Installed models', 'Remote models', 'Capability mapping', 'Resource hints'],
  jobs: ['Run queue', 'Progress events', 'Logs', 'History'],
  assets: ['Audio', 'Images', 'Transcripts', 'Reports', 'Checkpoints'],
  reports: ['Run reports', 'RPG autoplay evidence', 'Diagnostics exports', 'Generated documents'],
  settings: ['Global settings', 'Provider settings', 'Model settings', 'Local services'],
  diagnostics: ['Health checks', 'Event stream', 'Logs', 'Troubleshooting'],
};

export function ModuleWorkspace({ module }: { module: OmnixModuleDefinition }) {
  if (module.id === 'rpg') return <RpgWorkspace module={module} />;
  if (module.id === 'chatbot') return <ChatbotWorkspace module={module} />;
  if (module.id === 'podcast') return <PodcastWorkspace module={module} />;
  if (module.id === 'voice') return <VoiceWorkspace module={module} />;
  if (module.id === 'voice-cloning') return <VoiceCloningWorkspace module={module} />;
  if (module.id === 'stt') return <SttWorkspace module={module} />;
  if (module.id === 'image-generation') return <ImageGenerationWorkspace module={module} />;
  if (module.id === 'storyteller') return <StorytellerWorkspace module={module} />;
  if (module.id === 'trading') return <TradingWorkspace module={module} />;
  if (module.id === 'settings') return <SettingsWorkspace module={module} />;
  if (isPlatformModule(module.id)) return <PlatformModuleWorkspace module={module} />;

  const capabilities = moduleCapabilities[module.id] ?? [];
  return (
    <WorkspacePanel>
      <div className="workspace-heading">
        <div><p className="eyebrow">Module workspace</p><h2 id="module-title">{module.label}</h2></div>
        <code>{module.route}</code>
      </div>
      <p className="workspace-summary">{module.summary}</p>
      <div className="workspace-grid">
        <article>
          <h4>Infrastructure contract</h4>
          <ul>
            <li>Uses the shared app shell.</li><li>Uses the shared typed API client.</li>
            <li>Uses the shared event client for streaming/progress.</li>
            <li>Uses shared jobs, assets, providers, diagnostics, and design primitives.</li>
          </ul>
        </article>
        <article><h4>Module capabilities</h4><ul>{capabilities.map((capability) => <li key={capability}>{capability}</li>)}</ul></article>
      </div>
    </WorkspacePanel>
  );
}
