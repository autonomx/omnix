/**
 * LM Studio Chatbot - TTS Queue
 * Manages TTS audio queuing and sequential playback
 */

console.log('[TTS-QUEUE] Starting to load...');

try {

// Global audio playback control
let globalAudioPlayQueue = [];

// Streaming TTS WebSocket connection
let ttsWebSocket = null;

// ============================================================
// WEB AUDIO API STREAMING (Gapless playback)
// ============================================================

let streamingAudioContext = null;
let currentSource = null;
let streamingSampleRate = 24000;
let isPlaying = false;
let pendingChunks = []; // Chunks waiting to be played

/**
 * Initialize Web Audio context for streaming playback
 */
function initStreamingAudio() {
    if (!streamingAudioContext) {
        streamingAudioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: streamingSampleRate
        });
    }
    if (streamingAudioContext.state === 'suspended') {
        streamingAudioContext.resume();
    }
}

/**
 * Convert base64 PCM to float32 samples
 */
function base64ToFloat32(b64) {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
    }
    const int16 = new Int16Array(bytes.buffer);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
        float32[i] = int16[i] / 32768.0;
    }
    return float32;
}

/**
 * Play next pending chunk in the queue
 */
function playNextPendingChunk() {
    // Stop requested
    if (typeof window.stopAudioRequested !== 'undefined' && window.stopAudioRequested) {
        pendingChunks = [];
        isPlaying = false;
        if (typeof window.conversationMode !== 'undefined' && window.conversationMode) {
            if (typeof updateConversationStatus === 'function') updateConversationStatus('Ready to chat');
            if (typeof showCircleIndicator === 'function') showCircleIndicator('idle');
        }
        return;
    }
    
    if (pendingChunks.length === 0) {
        isPlaying = false;
        if (window.VoiceState) window.VoiceState.assistantSpeaking = false;
        // Trigger cooldown so VAD doesn't immediately pick up room noise or
        // speaker echo after playback ends
        if (typeof window.triggerTTSCooldown === 'function') window.triggerTTSCooldown();
        if (typeof window.conversationMode !== 'undefined' && window.conversationMode) {
            if (typeof updateConversationStatus === 'function') updateConversationStatus('Ready to chat');
            if (typeof showCircleIndicator === 'function') showCircleIndicator('idle');
        }
        return;
    }
    
    const float32Chunk = pendingChunks.shift();
    initStreamingAudio();
    
    // Create AudioBuffer for this chunk
    const audioBuffer = streamingAudioContext.createBuffer(
        1, 
        float32Chunk.length, 
        streamingSampleRate
    );
    audioBuffer.copyToChannel(float32Chunk, 0);
    
    // Create and start source
    currentSource = streamingAudioContext.createBufferSource();
    currentSource.buffer = audioBuffer;
    currentSource.connect(streamingAudioContext.destination);
    
    currentSource.onended = () => {
        // Play next chunk immediately
        playNextPendingChunk();
    };
    
    currentSource.start();
}

/**
 * Stop streaming audio playback
 */
function stopStreamingAudio() {
    if (currentSource) {
        try {
            currentSource.stop();
        } catch (e) {}
        currentSource = null;
    }
    isPlaying = false;
    pendingChunks = [];
    globalAudioPlayQueue = [];
}

let audioWorkletNode = null;

function stopTTSPlayback() {
    if (audioWorkletNode && audioWorkletNode.port) {
        audioWorkletNode.port.postMessage({
            type: "reset"
        });
    }
    
    stopStreamingAudio();
    
    if (typeof window.conversationMode !== 'undefined' && window.conversationMode) {
        if (typeof updateConversationStatus === 'function') {
            updateConversationStatus('Ready to chat');
        }
        if (typeof showCircleIndicator === 'function') {
            showCircleIndicator('idle');
        }
    }
    
    if (typeof window !== 'undefined') {
        window.stopAudioRequested = true;
    }
    
    isSpeaking = false;
    if (typeof window !== 'undefined') {
        window.VoiceState.assistantSpeaking = false;
    }
}

window.stopTTSPlayback = stopTTSPlayback;

// Export for external use
window.stopStreamingAudio = stopStreamingAudio;

/**
 * Enqueue audio chunk for streaming playback (gapless)
 * @param {string} audioBase64 - Base64 encoded PCM data
 * @param {number} sampleRate - Sample rate of the audio
 */
function enqueueAudio(audioBase64, sampleRate) {
    // Stop requested - don't play
    if (typeof window.stopAudioRequested !== 'undefined' && window.stopAudioRequested) {
        return;
    }
    
    streamingSampleRate = sampleRate || 24000;
    
    // Convert base64 PCM to float32
    const float32Chunk = base64ToFloat32(audioBase64);
    
    if (typeof window.conversationMode !== 'undefined' && window.conversationMode) {
        if (typeof updateConversationStatus === 'function') updateConversationStatus('🔊 Speaking...', 'speaking');
        if (typeof showCircleIndicator === 'function') showCircleIndicator('speaking');
    }
    
    // Add to pending chunks
    pendingChunks.push(float32Chunk);
    
    // Start playback if not already playing
    if (!isPlaying) {
        isPlaying = true;
        if (window.VoiceState) window.VoiceState.assistantSpeaking = true;
        playNextPendingChunk();
    }
}

// ============================================================
// WEBSOCKET TTS (Streaming via /ws/tts)
// ============================================================

/**
 * Connect to streaming TTS WebSocket
 */
function connectTTSWebSocket() {
    return new Promise((resolve, reject) => {
        if (ttsWebSocket && ttsWebSocket.readyState === WebSocket.OPEN) {
            resolve(ttsWebSocket);
            return;
        }
        
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.hostname}:${window.location.port || '5000'}/ws/tts`;
        ttsWebSocket = new WebSocket(wsUrl);
        ttsWebSocket.binaryType = 'arraybuffer';
        
        ttsWebSocket.onopen = () => {
            console.log('[TTS-WS] Connected');
            resolve(ttsWebSocket);
        };
        
        ttsWebSocket.onerror = (error) => {
            console.error('[TTS-WS] Error:', error);
            reject(error);
        };
        
        ttsWebSocket.onclose = () => {
            console.log('[TTS-WS] Closed');
            ttsWebSocket = null;
        };
        
        ttsWebSocket.onmessage = (event) => {
            try {
                if (event.data instanceof ArrayBuffer) {
                    // Binary frame: int16 PCM audio — queue for playback
                    window.AudioPlayer?.queueTTSChunk?.(event.data);
                } else {
                    const msg = JSON.parse(event.data);
                    console.log('[TTS-WS] Message:', msg.type);
                    
                    if (msg.type === 'done') {
                        console.log('[TTS-WS] Stream complete');
                    } else if (msg.type === 'error') {
                        console.error('[TTS-WS] Server error:', msg.error);
                    }
                }
            } catch (e) {
                console.error('[TTS-WS] Parse error:', e);
            }
        };
    });
}

/**
 * Stream TTS via WebSocket with HTTP fallback
 */
async function speakTextViaWebSocket(text, voiceCloneId = null) {
    console.log('[TTS-WS] speakTextViaWebSocket:', text.substring(0, 50));
    
    // Clear simple queue
    if (typeof window.AudioPlayer?.clearTTSQueue === 'function') {
        window.AudioPlayer.clearTTSQueue();
    }
    
    // Reset stop flag
    if (typeof stopAudioRequested !== 'undefined') {
        stopAudioRequested = false;
    }
    
    try {
        await connectTTSWebSocket();
        
        const request = {
            text: text,
            voice: voiceCloneId || 'default'
        };
        ttsWebSocket.send(JSON.stringify(request));
        console.log('[TTS-WS] Request sent');
        
        // Wait for completion (done message sets flag)
        return new Promise((resolve) => {
            const checkDone = () => {
                if (!window.AudioPlayer?.ttsIsPlayingQueue && 
                    window.AudioPlayer?.ttsAudioQueue?.length === 0) {
                    resolve();
                } else {
                    setTimeout(checkDone, 100);
                }
            };
            checkDone();
        });
        
    } catch (error) {
        console.error('[TTS-WS] WebSocket failed, falling back to HTTP:', error);
        // Fall back to batch TTS
        if (typeof speakText === 'function') {
            await speakText(text, voiceCloneId);
        }
    }
}

/**
 * Clear the audio queue and stop playback
 */
function clearAudioQueue() {
    globalAudioPlayQueue = [];
    globalAudioPlaying = false;
    if (typeof window.AudioPlayer?.clearTTSQueue === 'function') {
        window.AudioPlayer.clearTTSQueue();
    }
}

// Export for use in other modules
window.TTSQueue = {
    enqueueAudio,
    playNextAudio: () => {}, // Legacy stub
    clearAudioQueue,
    connectTTSWebSocket,
    speakTextViaWebSocket
};

console.log('[TTS-QUEUE] Loaded and ready');

} catch (e) {
    console.error('[TTS-QUEUE] Error loading:', e);
}