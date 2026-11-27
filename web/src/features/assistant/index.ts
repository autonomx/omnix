/** The assistant feature's public API (WP-9.7). */
export { chatbotModule } from './module';
// The read-aloud player's audio worklet as a PCM16 stream heard as it arrives: the RPG's responses and Storyteller's
// pages are spoken into it.
export { openPcmSink, type PcmSink } from './workspace/pcm-stream-sink';
// A podcast's live avatars (D4): its cast's portraits, and its lines spoken through the live voice socket.
export { CastPortraitLoadControl } from './chat/portrait/CastPortraitLoadControl';
export { CharacterStage, isPortraitPack, listCastableCharacters, type CastableCharacter, type StageCharacter } from './chat/portrait/CharacterStage';
export { speakAsCharacters, type CharacterLine, type CharacterSpeechRun } from './workspace/character-speech-player';
