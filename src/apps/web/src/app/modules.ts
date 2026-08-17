export type OmnixModuleId =
  | 'rpg'
  | 'chatbot'
  | 'storyteller'
  | 'podcast'
  | 'voice'
  | 'voice-cloning'
  | 'stt'
  | 'image-generation'
  | 'trading'
  | 'providers'
  | 'models'
  | 'jobs'
  | 'assets'
  | 'reports'
  | 'settings'
  | 'diagnostics';

export type OmnixModuleRoute =
  | '/rpg'
  | '/chatbot'
  | '/storyteller'
  | '/podcast'
  | '/voice'
  | '/voice-cloning'
  | '/stt'
  | '/image-generation'
  | '/trading'
  | '/providers'
  | '/models'
  | '/jobs'
  | '/assets'
  | '/reports'
  | '/settings'
  | '/diagnostics';

export interface OmnixModuleDefinition {
  id: OmnixModuleId;
  label: string;
  summary: string;
  route: OmnixModuleRoute;
}

export const omnixModules: OmnixModuleDefinition[] = [
  { id: 'rpg', label: 'RPG', summary: 'Deterministic AI role-playing engine, turn contracts, journal, party, combat, and reports.', route: '/rpg' },
  { id: 'chatbot', label: 'Chatbot', summary: 'Text chat using the shared provider and model registry.', route: '/chatbot' },
  { id: 'storyteller', label: 'Storyteller', summary: 'Long-form story generation, outlines, branches, and exports.', route: '/storyteller' },
  { id: 'podcast', label: 'Podcast', summary: 'Script planning, multi-speaker synthesis, mixing, and podcast exports.', route: '/podcast' },
  { id: 'voice', label: 'Voice Studio', summary: 'Text-to-speech generation, previews, playback, and voice provider diagnostics.', route: '/voice' },
  { id: 'voice-cloning', label: 'Voice Cloning', summary: 'Voice profile creation, sample ingestion, previews, and profile metadata.', route: '/voice-cloning' },
  { id: 'stt', label: 'STT', summary: 'Speech-to-text transcription, alignment, transcript assets, and diagnostics.', route: '/stt' },
  { id: 'image-generation', label: 'Image Generation', summary: 'Portraits, scenes, covers, image assets, and visual provider status.', route: '/image-generation' },
  {
    id: 'trading',
    label: 'Trading',
    summary: 'Multi-chart crypto and stock research, drawings, indicators, alerts, replay, backtests, and paper simulation.',
    route: '/trading',
  },
  { id: 'providers', label: 'Providers', summary: 'Shared provider registry, model discovery, health, latency, and capabilities.', route: '/providers' },
  { id: 'models', label: 'Models', summary: 'Installed and remote models, capability mapping, defaults, and resource hints.', route: '/models' },
  { id: 'jobs', label: 'Jobs / Runs', summary: 'Shared long-running job queue, run history, progress, and logs.', route: '/jobs' },
  { id: 'assets', label: 'Assets', summary: 'Generated audio, images, transcripts, reports, checkpoints, and exports.', route: '/assets' },
  { id: 'reports', label: 'Reports', summary: 'Run reports, RPG autoplay evidence, diagnostics exports, and generated documents.', route: '/reports' },
  { id: 'settings', label: 'Settings', summary: 'Global app, provider, model, local service, and feature settings.', route: '/settings' },
  { id: 'diagnostics', label: 'Diagnostics', summary: 'Health checks, logs, event stream status, and troubleshooting surfaces.', route: '/diagnostics' },
];
