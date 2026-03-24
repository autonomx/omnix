/**
 * LM Studio Chatbot - Audio Player
 * Handles WAV and Web Audio API playback with crossfading
 */


// Audio queue for sequential playback
let audioPlaybackQueue = [];
let isPlayingAudio = false;

// Cross-fade state for smooth chunk transitions
let previousChunkEndSamples = null;
let isFirstAudioChunk = true;

const TTS_SAMPLE_RATE = 24000;

// Crossfade configuration - 240 samples = ~10ms at 24kHz for smooth transitions
const CROSSFADE_SAMPLES = 240;

// Global AudioContext for Web Audio API playback
let webAudioContext = null;
let webAudioSourceNode = null;
let webAudioPlaying = false;
let webAudioQueue = [];
let webAudioStartTime = 0;
let webAudioNextStartTime = 0;

// Flag to use Web Audio API instead of Audio element
const USE_WEB_AUDIO_API = true;  // Set to true for lower latency

// Simple audio queue (like pocket-tts-server)
let ttsAudioQueue = [];
let ttsIsPlayingQueue = false;
let ttsCurrentAudio = null;

// ============================================================
// WEB AUDIO API PLAYBACK (Lower Latency Alternative)
// ============================================================

/**
 * Initialize or get the Web Audio API context
 * This provides lower latency and more control than Audio elements
 */
function getWebAudioContext() {
    if (!webAudioContext) {
        webAudioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: TTS_SAMPLE_RATE,
            latencyHint: 'interactive'
        });
        console.log('[WEB_AUDIO] Initialized AudioContext:', webAudioContext.sampleRate + 'Hz');
    }
    
    // Resume if suspended (required by browsers after user interaction)
    if (webAudioContext.state === 'suspended') {
        webAudioContext.resume();
    }
    
    return webAudioContext;
}

/**
 * Play audio using Web Audio API with precise scheduling
 * @param {Float32Array} audioData - Audio samples as Float32Array (-1 to 1)
 * @param {number} sampleRate - Sample rate of the audio
 * @returns {Promise} Resolves when audio finishes playing
 */
function playWithWebAudio(audioData, sampleRate) {
    return new Promise((resolve) => {
        try {
            const ctx = getWebAudioContext();
            
            // Apply crossfade before scheduling
            const processedData = applyEqualPowerCrossfade(audioData, sampleRate);
            
            // Create buffer for this chunk
            const numSamples = processedData.length;
            const audioBuffer = ctx.createBuffer(1, numSamples, sampleRate);
            const channelData = audioBuffer.getChannelData(0);
            
            // Copy audio data
            channelData.set(processedData);
            
            // Create source node
            const source = ctx.createBufferSource();
            source.buffer = audioBuffer;
            
            // Connect to destination
            source.connect(ctx.destination);
            
            // Handle playback end
            source.onended = () => {
                resolve();
            };
            
            // PRECISE SCHEDULING: Always schedule with AudioContext time
            const currentTime = ctx.currentTime;
            
            // If nothing is playing, start now
            // Otherwise, schedule after the last chunk
            const startTime = Math.max(currentTime, webAudioNextStartTime);
            source.start(startTime);
            
            // Update the time for the next chunk
            const duration = numSamples / sampleRate;
            webAudioNextStartTime = startTime + duration;
            
            console.log(`[WEB_AUDIO] Scheduled ${numSamples} samples at ${startTime.toFixed(3)}s, duration=${duration.toFixed(3)}s, next=${webAudioNextStartTime.toFixed(3)}s`);
            
        } catch (error) {
            console.error('[WEB_AUDIO] Playback error:', error);
            resolve();
        }
    });
}

/**
 * Apply equal-power crossfade for smooth chunk transitions
 * Uses cos/sin curves for constant power during fade
 * CRITICAL FIX: Save ORIGINAL end samples BEFORE crossfade to avoid cumulative distortion
 * @param {Float32Array} audioData - Audio samples
 * @param {number} sampleRate - Sample rate
 * @returns {Float32Array} Processed audio with crossfade applied
 */
function applyEqualPowerCrossfade(audioData, sampleRate) {
    const numSamples = audioData.length;
    const crossfadeLen = Math.min(CROSSFADE_SAMPLES, Math.floor(numSamples / 4));
    
    // Create output buffer
    const output = new Float32Array(numSamples);
    output.set(audioData);
    
    // IMPORTANT: Save ORIGINAL end samples BEFORE any modification
    // This prevents cumulative distortion from crossfading already-crossfaded data
    const originalEndSamples = new Float32Array(crossfadeLen);
    for (let i = 0; i < crossfadeLen; i++) {
        originalEndSamples[i] = audioData[numSamples - crossfadeLen + i];
    }
    
    // Apply fade-in to first chunk to avoid startup click
    if (isFirstAudioChunk) {
        const fadeInLen = Math.min(144, Math.floor(numSamples / 8));
        for (let i = 0; i < fadeInLen; i++) {
            const t = i / fadeInLen;
            // Equal-power fade in
            output[i] = audioData[i] * Math.sin(t * Math.PI / 2);
        }
        isFirstAudioChunk = false;
    }
    
    // Cross-fade start of this chunk with end of previous chunk
    if (previousChunkEndSamples && previousChunkEndSamples.length === crossfadeLen) {
        for (let i = 0; i < crossfadeLen; i++) {
            const t = i / crossfadeLen;
            // Equal-power cross-fade: cos for fade out, sin for fade in
            const fadeOut = Math.cos(t * Math.PI / 2);
            const fadeIn = Math.sin(t * Math.PI / 2);
            // Blend previous chunk end with current chunk start
            output[i] = previousChunkEndSamples[i] * fadeOut + audioData[i] * fadeIn;
        }
    }
    
    // Store ORIGINAL end samples for next chunk (not the modified ones!)
    previousChunkEndSamples = originalEndSamples;
    
    return output;
}

/**
 * Convert Int16 PCM to Float32 for Web Audio API
 * @param {Int16Array} int16Data - PCM data as 16-bit integers
 * @returns {Float32Array} Audio data as floats (-1 to 1)
 */
function int16ToFloat32(int16Data) {
    const float32 = new Float32Array(int16Data.length);
    for (let i = 0; i < int16Data.length; i++) {
        float32[i] = int16Data[i] / 32768.0;
    }
    return float32;
}

/**
 * Reset Web Audio API state for new TTS session
 */
function resetWebAudioState() {
    webAudioNextStartTime = 0;
    webAudioPlaying = false;
    webAudioQueue = [];
}

// ============================================================
// SIMPLE AUDIO QUEUE (Like pocket-tts-server)
// ============================================================

/**
 * Queue audio data and play sequentially
 * @param {string} audioBase64 - Base64 encoded complete WAV file
 */
function queueTTSChunk(audioBase64) {
    if (!audioBase64 || audioBase64.length < 100) {
        console.warn('[TTS-QUEUE] Invalid audio data');
        return;
    }
    
    ttsAudioQueue.push(audioBase64);
    console.log('[TTS-QUEUE] Audio queued, queue length:', ttsAudioQueue.length);
    
    // Start playing if not already
    playTTSQueue();
}

/**
 * Play audio queue sequentially using Web Audio API (single AudioContext)
 */
async function playTTSQueue() {
    if (ttsIsPlayingQueue || ttsAudioQueue.length === 0) return;
    
    ttsIsPlayingQueue = true;
    
    while (ttsAudioQueue.length > 0) {
        // Check if stop requested
        if (typeof stopAudioRequested !== 'undefined' && stopAudioRequested) {
            console.log('[TTS-QUEUE] Stop requested, clearing queue');
            ttsAudioQueue = [];
            if (ttsCurrentAudio) {
                try { ttsCurrentAudio.stop(); } catch (e) {}
                ttsCurrentAudio = null;
            }
            break;
        }
        
        const audioData = ttsAudioQueue.shift();
        
        try {
            const ctx = getWebAudioContext();

            // Decode base64 to binary
            const binaryString = atob(audioData);
            const len = binaryString.length;
            const uint8 = new Uint8Array(len);
            for (let i = 0; i < len; i++) {
                uint8[i] = binaryString.charCodeAt(i) & 0xFF;
            }

            // Decode WAV/audio data using AudioContext
            const audioBuffer = await ctx.decodeAudioData(uint8.buffer.slice(0));

            const source = ctx.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(ctx.destination);
            ttsCurrentAudio = source;

            // Use timeline scheduling for gapless playback
            const currentTime = ctx.currentTime;
            const startTime = Math.max(currentTime, webAudioNextStartTime);
            source.start(startTime);
            webAudioNextStartTime = startTime + audioBuffer.duration;

            // Wait for this chunk to finish before pulling next from queue
            await new Promise((resolve) => {
                source.onended = () => {
                    ttsCurrentAudio = null;
                    resolve();
                };
            });
        } catch (e) {
            console.error('[TTS-QUEUE] Playback error:', e);
            ttsCurrentAudio = null;
        }
    }
    
    ttsIsPlayingQueue = false;
    console.log('[TTS-QUEUE] Playback complete');
}

/**
 * Clear the TTS queue and stop playback
 */
function clearTTSQueue() {
    ttsAudioQueue = [];
    ttsIsPlayingQueue = false;
    ttsCurrentAudio = null;
    webAudioNextStartTime = 0;
    // Close and recreate context to kill all scheduled audio
    if (webAudioContext) {
        webAudioContext.close().catch(() => {});
        webAudioContext = null;
    }
}

// ============================================================
// PLAY TTS AUDIO (Main Entry Point)
// ============================================================

/**
 * Play TTS audio using Web Audio API (reuses a single AudioContext)
 * Returns a promise that resolves when playback is complete
 */
async function playTTS(audioBase64, sampleRate = null) {
    try {
        console.log('[TTS-PLAY] Starting playback function');
        
        // PHASE 3: GUARD - Skip WAV playback for stream/websocket modes
        if (window.TTS_PLAYBACK_MODE === "stream" || window.TTS_PLAYBACK_MODE === "websocket") {
            console.log("[TTS-PLAY] Skipping WAV playback (streaming mode active)");
            return;
        }
        
        // Check if stop was requested (from voice.js)
        if (typeof stopAudioRequested !== 'undefined' && stopAudioRequested) {
            console.log('[TTS-PLAY] Skipping playback - stop requested');
            return;
        }
        
        // Validate audio data
        if (!audioBase64 || audioBase64.length < 100) {
            console.error('[TTS-PLAY] Invalid audio data:', audioBase64?.length);
            return;
        }
        
        // Stop any currently-playing source on the shared context
        if (window.chatCurrentAudio) {
            try { window.chatCurrentAudio.stop(); } catch (e) {}
            window.chatCurrentAudio = null;
        }
        
        // Decode base64 to binary
        let arrayBuffer;
        try {
            const binaryString = atob(audioBase64);
            const len = binaryString.length;
            arrayBuffer = new ArrayBuffer(len);
            const uint8Array = new Uint8Array(arrayBuffer);
            for (let i = 0; i < len; i++) {
                uint8Array[i] = binaryString.charCodeAt(i) & 0xFF;
            }
            console.log('[TTS-PLAY] Decoded base64:', len, 'bytes');

            // If raw PCM (not RIFF/WAV), wrap in a WAV container
            if (!(uint8Array[0] === 0x52 && uint8Array[1] === 0x49 &&
                  uint8Array[2] === 0x46 && uint8Array[3] === 0x46) && sampleRate) {
                arrayBuffer = createWavBuffer(arrayBuffer, sampleRate);
                console.log('[TTS-PLAY] Created WAV container for raw PCM, sample rate:', sampleRate);
            }
        } catch (decodeError) {
            console.error('[TTS-PLAY] Base64 decode error:', decodeError);
            return;
        }

        const ctx = getWebAudioContext();
        const audioBuffer = await ctx.decodeAudioData(arrayBuffer.slice(0));
        console.log('[TTS-PLAY] Audio decoded, duration:', audioBuffer.duration);

        const source = ctx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(ctx.destination);

        window.chatCurrentAudio = source;

        await new Promise((resolve) => {
            source.onended = () => {
                console.log('[TTS-PLAY] Audio playback ended');
                window.chatCurrentAudio = null;
                if (typeof conversationMode !== 'undefined' && conversationMode) {
                    if (typeof micBtn !== 'undefined' && micBtn) micBtn.disabled = false;
                }
                resolve();
            };
            source.start();
            console.log('[TTS-PLAY] Audio.start() succeeded');
        });
        
    } catch (error) {
        console.error('[TTS-PLAY] Critical error in playTTS:', error);
        window.chatCurrentAudio = null;
        if (typeof conversationMode !== 'undefined' && conversationMode) {
            if (typeof micBtn !== 'undefined' && micBtn) micBtn.disabled = false;
        }
    }
}

/**
 * Direct audio playback using Web Audio API as fallback
 */
function playTTSWebAudio(audioBase64, sampleRate = 48000) {
    return new Promise((resolve, reject) => {
        try {
            console.log('[TTS-WEBAUDIO] Starting Web Audio playback');
            
            // Decode base64
            const binaryString = atob(audioBase64);
            const len = binaryString.length;
            const arrayBuffer = new ArrayBuffer(len);
            const uint8Array = new Uint8Array(arrayBuffer);
            for (let i = 0; i < len; i++) {
                uint8Array[i] = binaryString.charCodeAt(i);
            }
            
            // Check if it's a WAV file
            if (uint8Array[0] === 0x52 && uint8Array[1] === 0x49 && uint8Array[2] === 0x46 && uint8Array[3] === 0x46) {
                // Parse WAV header to get sample rate
                const header = new DataView(arrayBuffer, 0, 44);
                sampleRate = header.getUint32(24, true); // Sample rate from WAV header
                console.log('[TTS-WEBAUDIO] Detected WAV file, sample rate:', sampleRate);
            }
            
            // Create audio context
            const audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: sampleRate
            });
            
            // Resume if suspended
            if (audioContext.state === 'suspended') {
                audioContext.resume();
            }
            
            // Decode audio data
            audioContext.decodeAudioData(arrayBuffer.slice(0), (audioBuffer) => {
                console.log('[TTS-WEBAUDIO] Audio decoded, duration:', audioBuffer.duration);
                
                // Create source
                const source = audioContext.createBufferSource();
                source.buffer = audioBuffer;
                source.connect(audioContext.destination);
                
                // Play
                source.start();
                
                // Resolve when done
                source.onended = () => {
                    console.log('[TTS-WEBAUDIO] Web Audio playback completed');
                    resolve();
                };
                
            }, (error) => {
                console.error('[TTS-WEBAUDIO] Decode error:', error);
                resolve(); // Resolve anyway
            });
            
        } catch (error) {
            console.error('[TTS-WEBAUDIO] Web Audio playback error:', error);
            resolve(); // Resolve anyway
        }
    });
}

// ============================================================
// PCM CROSSFADE
// ============================================================

/**
 * Apply crossfade to PCM audio for smooth chunk transitions
 * CRITICAL FIX: Save ORIGINAL end samples BEFORE crossfade to avoid cumulative distortion
 */
function applyCrossfade(pcmBuffer, sampleRate) {
    const pcm16 = new Int16Array(pcmBuffer);
    const numSamples = pcm16.length;
    const float32 = new Float32Array(numSamples);
    
    // Convert to float32
    for (let i = 0; i < numSamples; i++) {
        float32[i] = pcm16[i] / 32768.0;
    }
    
    // Use longer crossfade for smoother transitions (reduced metallic artifact)
    const crossFadeLength = Math.min(CROSSFADE_SAMPLES, Math.floor(numSamples / 8)); // ~10ms at 48kHz
    const fadeLength = Math.min(144, Math.floor(numSamples / 4)); // ~3ms fade-in
    
    // IMPORTANT: Save ORIGINAL end samples BEFORE any modification
    // This prevents cumulative distortion from crossfading already-crossfaded data
    const originalEndSamples = new Float32Array(crossFadeLength);
    for (let i = 0; i < crossFadeLength; i++) {
        originalEndSamples[i] = float32[numSamples - crossFadeLength + i];
    }
    
    // Apply fade-in to first chunk to avoid startup click
    if (isFirstAudioChunk) {
        for (let i = 0; i < fadeLength; i++) {
            const t = i / fadeLength;
            // Equal-power fade in for smoother startup
            float32[i] *= Math.sin(t * Math.PI / 2);
        }
        isFirstAudioChunk = false;
    }
    
    // Cross-fade start of this chunk with end of previous chunk
    if (previousChunkEndSamples && previousChunkEndSamples.length === crossFadeLength) {
        for (let i = 0; i < crossFadeLength; i++) {
            const t = i / crossFadeLength;
            // Equal-power cross-fade for smoother transitions
            const fadeIn = Math.sin(t * Math.PI / 2);
            const fadeOut = Math.cos(t * Math.PI / 2);
            float32[i] = previousChunkEndSamples[i] * fadeOut + float32[i] * fadeIn;
        }
    }
    
    // Store ORIGINAL end samples for next chunk (not the modified ones!)
    previousChunkEndSamples = originalEndSamples;
    
    // Convert back to int16 PCM
    const result = new Int16Array(numSamples);
    for (let i = 0; i < numSamples; i++) {
        // Clamp to [-1, 1] and convert to 16-bit
        const sample = Math.max(-1, Math.min(1, float32[i]));
        result[i] = sample < 0 ? sample * 32768 : sample * 32767;
    }
    
    return result.buffer;
}

// Reset crossfade state when starting new TTS session
function resetCrossfadeState() {
    previousChunkEndSamples = null;
    isFirstAudioChunk = true;
}

// ============================================================
// WAV CREATION
// ============================================================

/**
 * Create WAV buffer from raw PCM - client-side for low latency
 */
function createWavBuffer(pcmData, sampleRate) {
    const numChannels = 1;
    const bitsPerSample = 16;
    const bytesPerSample = bitsPerSample / 8;
    const blockAlign = numChannels * bytesPerSample;
    const byteRate = sampleRate * blockAlign;
    const dataSize = pcmData.byteLength;
    const bufferSize = 44 + dataSize;
    
    const buffer = new ArrayBuffer(bufferSize);
    const view = new DataView(buffer);
    
    // RIFF header
    writeString(view, 0, 'RIFF');
    view.setUint32(4, 36 + dataSize, true);
    writeString(view, 8, 'WAVE');
    
    // fmt chunk
    writeString(view, 12, 'fmt ');
    view.setUint32(16, 16, true); // chunk size
    view.setUint16(20, 1, true); // audio format (PCM)
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, byteRate, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, bitsPerSample, true);
    
    // data chunk
    writeString(view, 36, 'data');
    view.setUint32(40, dataSize, true);
    
    // Copy PCM data
    const pcmView = new Uint8Array(pcmData);
    const offset = 44;
    for (let i = 0; i < pcmView.length; i++) {
        view.setUint8(offset + i, pcmView[i]);
    }
    
    return buffer;
}

function writeString(view, offset, string) {
    for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
    }
}

// Export for use in other modules
window.AudioPlayer = {
    playTTS,
    playTTSWebAudio,
    queueTTSChunk,
    playTTSQueue,
    clearTTSQueue,
    resetCrossfadeState,
    getWebAudioContext,
    playWithWebAudio,
    applyCrossfade,
    createWavBuffer,
    int16ToFloat32
};