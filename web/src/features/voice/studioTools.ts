/**
 * Voice Studio's tool rail. A tool appears once its roadmap phase ships
 * (`docs/architecture/OMNIX_VOICE_STUDIO_PARITY_ROADMAP.md`); unshipped tools
 * are hidden, not greyed out. Every tool opens in the studio's canvas, beside the rail (Dub shows the
 * dubbing app, which also has its own page).
 */
export const STUDIO_TOOLS = [
  { id: 'speak', label: 'Speak', summary: 'Write a script, cast voices and render speech.', shipped: true },
  { id: 'voices', label: 'Voices', summary: 'Your voice library and cloning.', shipped: true },
  { id: 'design', label: 'Design', summary: 'Create a voice from a description.', shipped: true },
  { id: 'transcribe', label: 'Transcribe', summary: 'Timed, speaker-labelled transcripts and subtitles.', shipped: true },
  { id: 'dub', label: 'Dub', summary: 'Translate and re-voice video.', shipped: true },
  { id: 'audio-tools', label: 'Audio Tools', summary: 'Isolate vocals, clean recordings, watermarks.', shipped: true },
  { id: 'batch', label: 'Batch', summary: 'Recipes, batch runs, watch folders and API clients.', shipped: true },
  { id: 'models', label: 'Models', summary: 'Install and manage speech models.', shipped: true },
] as const;

export type StudioToolId = (typeof STUDIO_TOOLS)[number]['id'];

export function shippedTools() {
  return STUDIO_TOOLS.filter((tool) => tool.shipped);
}

const TOOL_STORAGE_KEY = 'omnix.voice.studio.tool';

export function rememberedTool(): StudioToolId {
  try {
    const stored = typeof window !== 'undefined' ? window.localStorage.getItem(TOOL_STORAGE_KEY) : null;
    const tool = shippedTools().find((entry) => entry.id === stored);
    return tool?.id ?? 'speak';
  } catch {
    return 'speak';
  }
}

export function rememberTool(tool: StudioToolId): void {
  try {
    window.localStorage.setItem(TOOL_STORAGE_KEY, tool);
  } catch {
    // Private windows and blocked storage just forget the last tool.
  }
}
