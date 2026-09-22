import { lazy, Suspense, type ReactNode } from 'react';
import { isPlatformModule, type OmnixModuleDefinition } from '../app/modules';
import { WorkspacePanel } from '../design/primitives';

const RpgWorkspace = lazy(() => import('./rpg/RpgWorkspace').then((module) => ({ default: module.RpgWorkspace })));
const ChatbotWorkspace = lazy(() => import('./chatbot/ChatbotWorkspace').then((module) => ({ default: module.ChatbotWorkspace })));
const StorytellerWorkspace = lazy(() => import('./storyteller/StorytellerWorkspace').then((module) => ({ default: module.StorytellerWorkspace })));
const AudiobookWorkspace = lazy(() => import('./audiobook/AudiobookWorkspace').then((module) => ({ default: module.AudiobookWorkspace })));
const PodcastWorkspace = lazy(() => import('./podcast/PodcastWorkspace').then((module) => ({ default: module.PodcastWorkspace })));
const VoiceWorkspace = lazy(() => import('./voice/VoiceWorkspace').then((module) => ({ default: module.VoiceWorkspace })));
const VoiceCloningWorkspace = lazy(() => import('./voice-cloning/VoiceCloningWorkspace').then((module) => ({ default: module.VoiceCloningWorkspace })));
const SttWorkspace = lazy(() => import('./stt/SttWorkspace').then((module) => ({ default: module.SttWorkspace })));
const ImageGenerationWorkspace = lazy(() => import('./image-generation/ImageGenerationWorkspace').then((module) => ({ default: module.ImageGenerationWorkspace })));
const TradingWorkspace = lazy(() => import('./trading/TradingWorkspace').then((module) => ({ default: module.TradingWorkspace })));
const SettingsWorkspace = lazy(() => import('./platform/SettingsWorkspace').then((module) => ({ default: module.SettingsWorkspace })));
const PlatformModuleWorkspace = lazy(() => import('./platform/PlatformModuleWorkspace').then((module) => ({ default: module.PlatformModuleWorkspace })));

const moduleCapabilities: Record<string, string[]> = {
  rpg: ['Turn contracts', 'Deterministic state', 'Journal', 'Party', 'Combat', 'Autoplay reports'],
  chatbot: ['Shared provider selector', 'Streaming transcript', 'Conversation history', 'Prompt diagnostics'],
  storyteller: ['Story jobs', 'Outlines', 'Branches', 'Exports'],
  audiobook: ['Canonical source', 'Review queue', 'Voice casting', 'Chapter renders', 'Exports'],
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
  let content: ReactNode;
  if (module.id === 'rpg') content = <RpgWorkspace module={module} />;
  else if (module.id === 'chatbot') content = <ChatbotWorkspace module={module} />;
  else if (module.id === 'podcast') content = <PodcastWorkspace module={module} />;
  else if (module.id === 'voice') content = <VoiceWorkspace module={module} />;
  else if (module.id === 'voice-cloning') content = <VoiceCloningWorkspace module={module} />;
  else if (module.id === 'stt') content = <SttWorkspace module={module} />;
  else if (module.id === 'image-generation') content = <ImageGenerationWorkspace module={module} />;
  else if (module.id === 'storyteller') content = <StorytellerWorkspace module={module} />;
  else if (module.id === 'audiobook') content = <AudiobookWorkspace module={module} />;
  else if (module.id === 'trading') content = <TradingWorkspace module={module} />;
  else if (module.id === 'settings') content = <SettingsWorkspace module={module} />;
  else if (isPlatformModule(module.id)) content = <PlatformModuleWorkspace module={module} />;
  else {
    const capabilities = moduleCapabilities[module.id] ?? [];
    content = (
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
  return <Suspense fallback={<WorkspacePanel><p className="workspace-summary">Loading {module.label} workspace…</p></WorkspacePanel>}>{content}</Suspense>;
}
