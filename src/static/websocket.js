/**
 * LM Studio Chatbot - WebSocket Module
 * Streaming STT, TTS, and Voice Pipeline WebSocket connections
 */

// Streaming STT WebSocket
let sttWs = null;
let sttWsConnected = false;
let sttStreamingAudioChunks = [];

const WS_PROTOCOL = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const STT_WS_URL = `${WS_PROTOCOL}//${window.location.hostname}:8000/ws/transcribe`;

// Unified Voice WebSocket (STT + LLM + TTS)
let voiceWs = null;
let voiceWsConnected = false;
let voiceAudioBuffer = [];

// const VOICE_WS_URL = "ws://localhost:8001/ws/voice"; // Removed - no longer using realtime server

// Streaming TTS WebSocket
let ttsWs = null;
let ttsWsConnected = false;
let ttsAudioBuffer = [];

const TTS_WS_URL = `${WS_PROTOCOL}//${window.location.hostname}:8020/ws/tts`;

// Voice pipeline state
let voiceResponseText = '';

// Performance metrics
let voiceStartTime = null;
let voiceFirstTokenTime = null;
let voiceFirstAudioTime = null;
let voiceChunkCount = 0;

// Audio streaming
let streamingAudioContext = null;
let streamingSource = null;
let audioChunkQueue = [];
let isPlayingAudioChunk = false;
let lastChunkEndTime = 0;
let previousChunkEnd = null; // For cross-fading
let nextChunkStartTime = 0; // Precise scheduling time for next chunk

// ============================================================
// STREAMING STT WEBSOCKET
// ============================================================

// Connect to streaming STT WebSocket
function connectStreamingSTT() {
    return new Promise((resolve, reject) => {
        if (sttWs && sttWs.readyState === WebSocket.OPEN) {
            resolve();
            return;
        }
        
        try {
            sttWs = new WebSocket(STT_WS_URL);
            
            sttWs.onopen = () => {
                console.log('Streaming STT WebSocket connected');
                sttWsConnected = true;
                resolve();
            };
            
            sttWs.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    
                    if (data.type === 'ready') {
                        console.log('STT ready for streaming');
                    } else if (data.type === 'text' || data.type === 'done') {
                        // Update the input with transcribed text
                        // 'text' for partial results, 'done' for final result
                        const text = data.text || '';
                        if (conversationMode && conversationInput) {
                            conversationInput.value = text;
                            conversationSendBtn.disabled = !text.trim();
                        } else if (messageInput) {
                            messageInput.value = text;
                            sendBtn.disabled = !text.trim();
                        }
                        
                        if (data.type === 'done') {
                            console.log('STT streaming done, text:', text);
                        }
                    } else if (data.type === 'error') {
                        console.error('STT streaming error:', data.error);
                    }
                } catch (e) {
                    console.error('Error parsing STT message:', e);
                }
            };
            
            sttWs.onerror = (error) => {
                console.error('STT WebSocket error:', error);
                sttWsConnected = false;
                reject(error);
            };
            
            sttWs.onclose = () => {
                console.log('STT WebSocket closed');
                sttWsConnected = false;
                sttWs = null;
            };
            
            // Timeout for connection
            setTimeout(() => {
                if (!sttWsConnected) {
                    reject(new Error('Connection timeout'));
                }
            }, 5000);
            
        } catch (e) {
            reject(e);
        }
    });
}

// Send audio chunk to streaming STT
async function sendAudioChunkToStreamingSTT(audioBlob) {
    if (!sttWs || sttWs.readyState !== WebSocket.OPEN) {
        try {
            await connectStreamingSTT();
        } catch (e) {
            console.error('Failed to connect to streaming STT:', e);
            return;
        }
    }
    
    // Convert audio to base64
    const reader = new FileReader();
    reader.onload = () => {
        const base64 = reader.result.split(',')[1];
        
        if (sttWs && sttWs.readyState === WebSocket.OPEN) {
            sttWs.send(JSON.stringify({
                type: 'audio',
                data: base64
            }));
        }
    };
    reader.readAsDataURL(audioBlob);
}

// Send final signal to streaming STT
async function finalizeStreamingSTT() {
    if (sttWs && sttWs.readyState === WebSocket.OPEN) {
        sttWs.send(JSON.stringify({
            type: 'final'
        }));
    }
}

// Close streaming STT connection
function closeStreamingSTT() {
    if (sttWs) {
        sttWs.close();
        sttWs = null;
        sttWsConnected = false;
    }
}

// ============================================================
// STREAMING TTS WEBSOCKET
// ============================================================

// Connect to streaming TTS WebSocket
function connectStreamingTTS() {
    return new Promise((resolve, reject) => {
        if (ttsWs && ttsWs.readyState === WebSocket.OPEN) {
            resolve();
            return;
        }
        
        try {
            ttsWs = new WebSocket(TTS_WS_URL);
            
            ttsWs.onopen = () => {
                console.log('Streaming TTS WebSocket connected');
                ttsWsConnected = true;
                resolve();
            };
            
            ttsWs.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    
                    if (data.type === 'audio') {
                        // Add audio chunk to buffer
                        ttsAudioBuffer.push(data.data);
                        
                        // Play audio chunk immediately (streaming playback)
                        playStreamingAudioChunk(data.data, data.sample_rate);
                    } else if (data.type === 'done') {
                        console.log('TTS streaming done');
                        if (conversationMode) {
                            if (alwaysListening) {
                                showCircleIndicator('listening');
                                updateConversationStatus('🎤 Auto-listening - Speak now!', 'listening');
                            } else {
                                showCircleIndicator('idle');
                                updateConversationStatus('Ready to chat');
                            }
                        }
                        ttsAudioBuffer = [];
                    } else if (data.type === 'error') {
                        console.error('TTS streaming error:', data.data);
                        if (conversationMode) {
                            showCircleIndicator('idle');
                            updateConversationStatus('Ready to chat');
                        }
                    }
                } catch (e) {
                    console.error('Error parsing TTS message:', e);
                }
            };
            
            ttsWs.onerror = (error) => {
                console.error('TTS WebSocket error:', error);
                ttsWsConnected = false;
                reject(error);
            };
            
            ttsWs.onclose = () => {
                console.log('TTS WebSocket closed');
                ttsWsConnected = false;
                ttsWs = null;
            };
            
            // Timeout for connection
            setTimeout(() => {
                if (!ttsWsConnected) {
                    reject(new Error('Connection timeout'));
                }
            }, 5000);
            
        } catch (e) {
            reject(e);
        }
    });
}

// Play streaming audio chunk immediately (schedule directly, no queue wait)
async function playStreamingAudioChunk(audioBase64, sampleRate = 24000) {
    // Check if stop was requested
    if (typeof stopAudioRequested !== 'undefined' && stopAudioRequested) {
        console.log('[WS-AUDIO] Skipping chunk - stop requested');
        return;
    }
    
    // Schedule this chunk immediately - don't wait for queue
    // This ensures gapless playback by scheduling as soon as we receive data
    await scheduleAudioChunk(audioBase64, sampleRate);
}

// Direct scheduling function - schedules chunk immediately using Web Audio API
async function scheduleAudioChunk(audioBase64, sampleRate) {
    // PHASE 2: GUARD - Only schedule audio in websocket mode
    if (window.TTS_PLAYBACK_MODE !== "websocket") {
        console.log("[WS-AUDIO] Skipping AudioContext scheduling (WAV mode active)");
        return;
    }
    
    console.log('[WS-AUDIO] Streaming playback active');
    
    // Track if this is the first chunk
    const isFirstChunk = (previousChunkEnd === null);
    
    try {
        // Decode base64 to bytes
        const audioBytes = atob(audioBase64);
        const arrayBuffer = new ArrayBuffer(audioBytes.length);
        const uint8Array = new Uint8Array(arrayBuffer);
        for (let i = 0; i < audioBytes.length; i++) {
            uint8Array[i] = audioBytes.charCodeAt(i);
        }
        
        // Create audio context if needed - use browser's native sample rate (usually 48kHz)
        // PHASE 7: Don't force 24kHz - let browser use native rate to avoid resampling artifacts
        if (!streamingAudioContext) {
            streamingAudioContext = new (window.AudioContext || window.webkitAudioContext)({
                latencyHint: 'interactive'
            });
            console.log('[WS-AUDIO] Created AudioContext at native', streamingAudioContext.sampleRate + 'Hz');
        }
        
        // Resume audio context if suspended (browser autoplay policy)
        if (streamingAudioContext.state === 'suspended') {
            await streamingAudioContext.resume();
        }
        
        // Convert PCM16 to float32
        let buffer = uint8Array.buffer;
        if (buffer.byteLength % 2 !== 0) {
            const paddedBuffer = new ArrayBuffer(buffer.byteLength + 1);
            new Uint8Array(paddedBuffer).set(uint8Array);
            buffer = paddedBuffer;
        }
        
        const pcm16 = new Int16Array(buffer);
        const numSamples = pcm16.length;
        const float32 = new Float32Array(numSamples);
        
        for (let i = 0; i < numSamples; i++) {
            float32[i] = pcm16[i] / 32768.0;
        }
        
        // Apply fade-in to first chunk only (avoid startup click)
        if (isFirstChunk) {
            const fadeLength = Math.min(144, Math.floor(numSamples / 8)); // ~6ms fade
            for (let i = 0; i < fadeLength; i++) {
                float32[i] *= i / fadeLength;
            }
        }
        
        // Apply short fade-out to EVERY chunk to avoid click at end
        // Each sentence is generated independently, so add small fade at boundaries
        const fadeOutLength = Math.min(48, Math.floor(numSamples / 16)); // ~2ms fade
        for (let i = 0; i < fadeOutLength; i++) {
            const t = 1 - (i / fadeOutLength);
            float32[numSamples - fadeOutLength + i] *= t;
        }
        
        // Apply short fade-in to all NON-FIRST chunks
        if (!isFirstChunk) {
            const fadeInLength = Math.min(48, Math.floor(numSamples / 16)); // ~2ms fade
            for (let i = 0; i < fadeInLength; i++) {
                float32[i] *= i / fadeInLength;
            }
        }
        
        // Create audio buffer
        const audioBuffer = streamingAudioContext.createBuffer(1, float32.length, sampleRate);
        audioBuffer.getChannelData(0).set(float32);
        
        // Create source
        const source = streamingAudioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(streamingAudioContext.destination);
        
        // PRECISE SCHEDULING: Use AudioContext time for gapless playback
        const currentTime = streamingAudioContext.currentTime;
        const duration = numSamples / sampleRate;
        
        // First chunk plays now, subsequent chunks scheduled after previous
        const startTime = isFirstChunk ? currentTime : Math.max(currentTime, nextChunkStartTime);
        source.start(startTime);
        
        // Track when this chunk ends for next chunk scheduling
        nextChunkStartTime = startTime + duration;
        
    } catch (error) {
        console.error('[WS-AUDIO] Error scheduling chunk:', error);
    }
}

async function playNextAudioChunk() {
    // Check if stop was requested
    if (typeof stopAudioRequested !== 'undefined' && stopAudioRequested) {
        console.log('[WS-AUDIO] Stopping playback - stop requested');
        audioChunkQueue = [];
        isPlayingAudioChunk = false;
        previousChunkEnd = null;
        nextChunkStartTime = 0; // Reset scheduling time
        return;
    }
    
    if (audioChunkQueue.length === 0) {
        isPlayingAudioChunk = false;
        previousChunkEnd = null;
        nextChunkStartTime = 0; // Reset scheduling time for next session
        return;
    }
    
    isPlayingAudioChunk = true;
    const { audioBase64, sampleRate } = audioChunkQueue.shift();
    
    // Track if this is the first chunk
    const isFirstChunk = (previousChunkEnd === null);
    
    try {
        // Decode base64 to bytes
        const audioBytes = atob(audioBase64);
        const arrayBuffer = new ArrayBuffer(audioBytes.length);
        const uint8Array = new Uint8Array(arrayBuffer);
        for (let i = 0; i < audioBytes.length; i++) {
            uint8Array[i] = audioBytes.charCodeAt(i);
        }
        
        // Create audio context if needed - use same sample rate as TTS server (24kHz)
        if (!streamingAudioContext) {
            // IMPORTANT: Match the TTS server's sample rate to avoid resampling artifacts
            streamingAudioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: sampleRate || 24000,
                latencyHint: 'interactive'
            });
            console.log('[WS-AUDIO] Created AudioContext at', streamingAudioContext.sampleRate + 'Hz');
        }
        
        // Resume audio context if suspended (browser autoplay policy)
        if (streamingAudioContext.state === 'suspended') {
            await streamingAudioContext.resume();
        }
        
        // Convert PCM16 to float32 with proper handling
        let buffer = uint8Array.buffer;
        if (buffer.byteLength % 2 !== 0) {
            const paddedBuffer = new ArrayBuffer(buffer.byteLength + 1);
            new Uint8Array(paddedBuffer).set(uint8Array);
            buffer = paddedBuffer;
        }
        
        const pcm16 = new Int16Array(buffer);
        const numSamples = pcm16.length;
        const float32 = new Float32Array(numSamples);
        
        // Convert to float32 - use proper scaling for signed 16-bit
        // Scale by 1/32768 for symmetric range
        for (let i = 0; i < numSamples; i++) {
            float32[i] = pcm16[i] / 32768.0;
        }
        
        // Only apply fade-in to the FIRST chunk to avoid startup click
        if (isFirstChunk) {
            const fadeLength = Math.min(64, Math.floor(numSamples / 4)); // ~2.7ms fade
            for (let i = 0; i < fadeLength; i++) {
                const t = i / fadeLength;
                float32[i] *= t; // Linear fade-in
            }
        }
        
        // Save end of this chunk BEFORE any modifications for cross-fade with next chunk
        const crossFadeLength = Math.min(32, Math.floor(numSamples / 32)); // ~1.3ms
        
        // Save the raw end samples for cross-fading with the next chunk
        const chunkEnd = new Float32Array(crossFadeLength);
        for (let i = 0; i < crossFadeLength; i++) {
            chunkEnd[i] = float32[numSamples - crossFadeLength + i];
        }
        
        // Cross-fade start of this chunk with end of previous chunk
        if (previousChunkEnd && previousChunkEnd.length === crossFadeLength) {
            for (let i = 0; i < crossFadeLength; i++) {
                const t = i / crossFadeLength;
                // Equal-power cross-fade for smoother transitions
                const fadeIn = Math.sin(t * Math.PI / 2);
                const fadeOut = Math.cos(t * Math.PI / 2);
                float32[i] = previousChunkEnd[i] * fadeOut + float32[i] * fadeIn;
            }
        }
        
        // Store end samples for next chunk's cross-fade
        previousChunkEnd = chunkEnd;
        
        const audioBuffer = streamingAudioContext.createBuffer(1, float32.length, sampleRate);
        audioBuffer.getChannelData(0).set(float32);
        
        // Create and play source
        const source = streamingAudioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(streamingAudioContext.destination);
        
        // PRECISE SCHEDULING: Schedule chunk to play immediately after the previous one
        const currentTime = streamingAudioContext.currentTime;
        const duration = numSamples / sampleRate;
        
        // Start immediately if first chunk, otherwise schedule after previous
        const startTime = isFirstChunk ? currentTime : Math.max(currentTime, nextChunkStartTime);
        source.start(startTime);
        
        // Update the time for the next chunk
        nextChunkStartTime = startTime + duration;
        
        console.log(`[WS-AUDIO] Scheduled ${numSamples} samples at ${startTime.toFixed(3)}s, duration=${duration.toFixed(3)}s, next=${nextChunkStartTime.toFixed(3)}s`);
        
        source.onended = () => {
            // Play next chunk when this one ends
            playNextAudioChunk();
        };
        
    } catch (error) {
        console.error('[AUDIO] Error playing chunk:', error);
        // Continue with next chunk even if this one failed
        playNextAudioChunk();
    }
}

// Send text to streaming TTS and get audio chunks
async function speakTextStreaming(text, speaker = 'en') {
    if (!text) return;
    
    if (conversationMode) {
        micBtn.disabled = true;
        if (conversationMode) {
            showCircleIndicator('speaking');
            updateConversationStatus('🔊 Speaking...', 'speaking');
        }
    }
    
    try {
        // Connect to streaming TTS
        await connectStreamingTTS();
        
        // Send text request
        if (ttsWs && ttsWs.readyState === WebSocket.OPEN) {
            ttsWs.send(JSON.stringify({
                text: text,
                voice: speaker
            }));
        } else {
            throw new Error('TTS WebSocket not connected');
        }
        
    } catch (error) {
        console.error('Streaming TTS Error:', error);
        // Fall back to batch TTS
        console.log('Falling back to batch TTS');
        await speakText(text, speaker);
        
        if (conversationMode) {
            showCircleIndicator('idle');
            updateConversationStatus('Ready to chat');
        }
    }
}

// Close streaming TTS connection
function closeStreamingTTS() {
    if (ttsWs) {
        ttsWs.close();
        ttsWs = null;
        ttsWsConnected = false;
    }
}

// ============================================================
// UNIFIED VOICE WEBSOCKET (Full Pipeline: STT → LLM → TTS)
// ============================================================

// Connect to unified voice WebSocket
function connectVoiceWebSocket() {
    return new Promise((resolve, reject) => {
        if (voiceWs && voiceWs.readyState === WebSocket.OPEN) {
            resolve();
            return;
        }
        
        try {
            // voiceWs = new WebSocket(VOICE_WS_URL); // Removed - no longer using realtime server
            throw new Error('Voice WebSocket no longer supported - use REST API instead');
            
            voiceWs.onopen = () => {
                console.log('Voice WebSocket connected');
                voiceWsConnected = true;
                
                // Send config
                voiceWs.send(JSON.stringify({
                    type: "config",
                    system_prompt: systemPromptInput ? systemPromptInput.value : "You are a helpful AI assistant.",
                    model: modelSelect ? modelSelect.value : "llama-3.3-70b-versatile"
                }));
                
                resolve();
            };
            
            voiceWs.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    
                    switch (data.type) {
                        case "status":
                            // Status updates: transcribing, thinking, speaking
                            updateConversationStatus(data.data, data.data);
                            break;
                            
                        case "transcript":
                            // STT result
                            if (conversationInput) {
                                conversationInput.value = data.data;
                            }
                            break;
                            
                        case "text":
                            // LLM response chunk - display immediately
                            handleVoiceTextChunk(data.data);
                            break;
                            
                        case "audio":
                            // TTS audio chunk - play immediately
                            voiceChunkCount++;
                            if (!voiceFirstAudioTime) {
                                voiceFirstAudioTime = performance.now();
                                console.log(`⏱️ [TIMING] First audio: ${(voiceFirstAudioTime - voiceStartTime).toFixed(0)}ms`);
                            }
                            playStreamingAudioChunk(data.data, data.sample_rate);
                            break;
                            
                        case "done":
                            // Full response complete
                            handleVoiceDone();
                            break;
                            
                        case "error":
                            console.error('Voice pipeline error:', data.data);
                            updateConversationStatus('Error: ' + data.data, '');
                            break;
                    }
                } catch (e) {
                    console.error('Error parsing voice message:', e);
                }
            };
            
            voiceWs.onerror = (error) => {
                console.error('Voice WebSocket error:', error);
                voiceWsConnected = false;
                reject(error);
            };
            
            voiceWs.onclose = () => {
                console.log('Voice WebSocket closed');
                voiceWsConnected = false;
                voiceWs = null;
            };
            
            // Timeout
            setTimeout(() => {
                if (!voiceWsConnected) {
                    reject(new Error('Connection timeout'));
                }
            }, 10000);
            
        } catch (e) {
            reject(e);
        }
    });
}

// Handle voice text chunk
function handleVoiceTextChunk(text) {
    // Track first token time
    if (!voiceFirstTokenTime) {
        voiceFirstTokenTime = performance.now();
        console.log(`⏱️ [TIMING] First token: ${(voiceFirstTokenTime - voiceStartTime).toFixed(0)}ms`);
    }
    
    voiceResponseText += text;
    
    // Check if we need to create an AI message placeholder
    const lastMessage = conversationMessages.lastElementChild;
    const needsNewMessage = !lastMessage || !lastMessage.classList.contains('ai');
    
    if (needsNewMessage) {
        // Create AI message placeholder
        addConversationMessage('ai', voiceResponseText);
    } else {
        // Update existing AI message
        const contentDiv = lastMessage.querySelector('.conversation-message-content');
        if (contentDiv) {
            contentDiv.textContent = voiceResponseText;
        }
    }
    conversationMessages.scrollTop = conversationMessages.scrollHeight;
}

// Handle voice done
function handleVoiceDone() {
    const totalTime = performance.now() - voiceStartTime;
    
    console.log(`⏱️ ========== TIMING SUMMARY ==========`);
    console.log(`⏱️ [TOTAL] Response time: ${totalTime.toFixed(0)}ms`);
    if (voiceFirstTokenTime) {
        console.log(`⏱️ [LLM] First token: ${(voiceFirstTokenTime - voiceStartTime).toFixed(0)}ms`);
    }
    if (voiceFirstAudioTime) {
        console.log(`⏱️ [TTS] First audio: ${(voiceFirstAudioTime - voiceStartTime).toFixed(0)}ms`);
    }
    console.log(`⏱️ [TTS] Audio chunks: ${voiceChunkCount}`);
    console.log(`⏱️ ====================================`);
    
    // Reset metrics
    voiceResponseText = '';
    voiceStartTime = null;
    voiceFirstTokenTime = null;
    voiceFirstAudioTime = null;
    voiceChunkCount = 0;
    
    isLoading = false; // Reset loading state so new messages can be sent
    
    if (conversationMode) {
        if (alwaysListening) {
            showCircleIndicator('listening');
            updateConversationStatus('🎤 Auto-listening - Speak now!', 'listening');
        } else {
            showCircleIndicator('idle');
            updateConversationStatus('Ready to chat');
        }
    }
}

// Send audio through unified voice pipeline
async function sendVoiceAudio(audioBlob) {
    if (!voiceWs || voiceWs.readyState !== WebSocket.OPEN) {
        try {
            await connectVoiceWebSocket();
        } catch (e) {
            console.error('Failed to connect to voice pipeline:', e);
            return false;
        }
    }
    
    // Convert to base64
    const reader = new FileReader();
    reader.onload = () => {
        const base64 = reader.result.split(',')[1];
        
        if (voiceWs && voiceWs.readyState === WebSocket.OPEN) {
            voiceWs.send(JSON.stringify({
                type: "audio",
                data: base64
            }));
        }
    };
    reader.readAsDataURL(audioBlob);
}

// Signal end of audio input
function sendVoiceAudioDone() {
    if (voiceWs && voiceWs.readyState === WebSocket.OPEN) {
        voiceWs.send(JSON.stringify({
            type: "audio_done"
        }));
    }
}

// Send text through unified voice pipeline
async function sendVoiceText(text) {
    if (!text.trim()) return;
    
    // Start timing
    voiceStartTime = performance.now();
    voiceFirstTokenTime = null;
    voiceFirstAudioTime = null;
    voiceChunkCount = 0;
    voiceResponseText = '';
    
    // Add user message to display
    addConversationMessage('user', text);
    conversationInput.value = '';
    
    // Update status
    updateConversationStatus('Thinking...', 'listening');
    if (conversationMode) {
        showCircleIndicator('listening');
    }
    
    // Connect if not connected
    if (!voiceWs || voiceWs.readyState !== WebSocket.OPEN) {
        try {
            await connectVoiceWebSocket();
        } catch (e) {
            console.error('Failed to connect to voice pipeline, falling back to REST:', e);
            // Fall back to REST API
            return await sendConversationMessageREST(text);
        }
    }
    
    // Send text
    if (voiceWs && voiceWs.readyState === WebSocket.OPEN) {
        voiceWs.send(JSON.stringify({
            type: "text",
            data: text
        }));
    }
}

// Close voice WebSocket
function closeVoiceWebSocket() {
    if (voiceWs) {
        voiceWs.close();
        voiceWs = null;
        voiceWsConnected = false;
    }
}