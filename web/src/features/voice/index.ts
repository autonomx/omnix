/** The voice feature's public API (WP-9.7). */
import type { components } from './api/generated';

export { installVoiceLibraryAssetFallback } from './voiceLibraryAssetFallback';
export { installVoiceLibraryFetchDiagnostics } from './voiceLibraryFetchDiagnostics';
export { voiceApiClient } from './api/voiceClient';
export type STTProxyResponse = components['schemas']['STTProxyResponse'];
// The clone panel and voice library, shared with the Voice Cloning sidebar module.
export { CloneVoicePanel } from './CloneVoicePanel';
export { VoiceLibraryGrid } from './VoiceLibraryGrid';
export { voiceAssetId, voiceAssetName, type VoiceAsset } from './voiceAssets';
export { TRANSCRIPT_LANGUAGES, transcriptLanguage } from './transcriptLanguages';
// Push-to-talk dictation with the batch engine, shared with the chat composer (Phase 7).
export { PushToTalkButton } from './PushToTalkButton';
