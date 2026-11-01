/** The assistant feature's public API (WP-9.7). */
export { chatbotModule } from './module';
// The read-aloud player's audio worklet: a PCM16 stream heard as it arrives (the RPG speaks its responses with it).
export { default as PCM_STREAM_WORKLET_URL } from './workspace/worklets/assistant-pcm-stream.worklet?worker&url';
export { ASSISTANT_PCM_STREAM_WORKLET_NAME as PCM_STREAM_WORKLET_NAME } from './workspace/worklets/names';
