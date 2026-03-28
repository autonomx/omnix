/**
 * LM Studio Chatbot - FastAPI WebSocket Client
 * Ultra-low-latency voice conversation using WebSocket + AudioWorklet
 * Replaces HTTP streaming with binary WebSocket for sub-500ms latency
 */

if (window.__WS_CLIENT_LOADED__) {
    console.warn('[WS-CLIENT] Already loaded, skipping duplicate injection');
} else {
window.__WS_CLIENT_LOADED__ = true;

console.log('[WS-CLIENT] Starting to load...');

// ============== CONFIG ==============
const WS_CONV_PROTOCOL = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_URL = `${WS_CONV_PROTOCOL}//${window.location.host}/ws/conversation`;
const SAMPLE_RATE = 24000;
let FRAME_SIZE = 1920;
const START_BUFFER_SAMPLES = 6000;

let pendingMessages = [];

// Single-flight guard: only one message may be in-flight at a time.
// Set when a message is sent or queued; cleared when the response is done/error/stopped.
let inFlightMessageId = null;

// Maximum number of samples that may be buffered for playback (~5 seconds at 48 kHz).
// Exceeding this cap causes the backlog to be dropped so the engine doesn't fall
// 40+ seconds behind the live audio stream.
const MAX_BUFFER_SAMPLES = 48000 * 5;

let pendingBuffer = new Float32Array(0);
let nativeSampleRate = 48000;

let wsAudioContext = null;
let pcmNode = null;
let wsGainNode = null;
let isConnected = false;
let isSpeaking = false;
let wsSessionId = null;
let currentSpeaker = 'default';

let startupBuffer = [];
let bufferedSamples = 0;
let playbackStarted = false;

let ws = null;

let totalStartTime = 0;
let llmFirstTokenTime = 0;
let firstAudioTime = 0;
let currentAssistantDiv = null;
let streamedContent = '';
let responseComplete = false;
let _audioGate = true;  // false after stopAudio() to block stale tts_audio chunks
let _workletSamplesQueued = 0;    // running total of samples posted to worklet this turn
let _drainCalledThisTurn = false; // prevents double-call of _onWorkletDrained

function mergeFloat32Arrays(arrays) {
    const total = arrays.reduce((sum, arr) => sum + arr.length, 0);
    const result = new Float32Array(total);
    let offset = 0;
    for (const arr of arrays) {
        result.set(arr, offset);
        offset += arr.length;
    }
    return result;
}

function shouldEmitChunk(buffer) {
    if (buffer.length > 25) return true;
    if (/[.,!?;:]$/.test(buffer)) return true;
    return false;
}

async function sendTextToTTS(text) {
    if (!ws || !isConnected) return;
    
    try {
        ws.send(JSON.stringify({
            type: 'tts_request',
            text: text
        }));
    } catch (e) {
        console.error('[WS-CLIENT] TTS request failed:', e);
    }
}

function appendSamples(samples) {
    const merged = new Float32Array(pendingBuffer.length + samples.length);
    merged.set(pendingBuffer, 0);
    merged.set(samples, pendingBuffer.length);
    pendingBuffer = merged;
}

function upsample24toNative(pcm24) {
    if (nativeSampleRate === SAMPLE_RATE) return pcm24;
    const factor = nativeSampleRate / SAMPLE_RATE;
    const outLen = Math.round(pcm24.length * factor);
    const out = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
        const srcPos = i / factor;
        const srcIdx = Math.floor(srcPos);
        const frac = srcPos - srcIdx;
        const s0 = pcm24[srcIdx] ?? 0;
        const s1 = pcm24[srcIdx + 1] ?? s0;
        out[i] = s0 + (s1 - s0) * frac;
    }
    return out;
}

function addWSSystemMessage(role, content) {
    const convChatView = document.getElementById('conversationChatView');
    const isConversationMode = convChatView && convChatView.classList.contains('active');
    
    if (isConversationMode) {
        const convMessages = document.getElementById('conversationMessages');
        if (convMessages) {
            const msgDiv = document.createElement('div');
            msgDiv.className = `conversation-message ${role}`;
            
            const avDiv = document.createElement('div');
            avDiv.className = 'conversation-message-avatar';
            avDiv.textContent = role === 'user' ? '👤' : '🤖';
            
            const contDiv = document.createElement('div');
            contDiv.className = 'conversation-message-content';
            contDiv.textContent = content;
            
            msgDiv.appendChild(avDiv);
            msgDiv.appendChild(contDiv);
            convMessages.appendChild(msgDiv);
            convMessages.scrollTop = convMessages.scrollHeight;
            return msgDiv;
        }
    }
    
    if (typeof addMessage === 'function') {
        return addMessage(role === 'user' ? 'user' : 'assistant', content);
    }
    return null;
}

// ============== AUDIOWORKLET SETUP ==============
async function initAudioWorklet() {
    if (wsAudioContext) return;

    wsAudioContext = new (window.AudioContext || window.webkitAudioContext)();
    nativeSampleRate = wsAudioContext.sampleRate;
    FRAME_SIZE = Math.round(0.02 * nativeSampleRate);

    await wsAudioContext.audioWorklet.addModule("/static/js/audio/pcm-player-worklet.js?v=" + Date.now());

    pcmNode = new AudioWorkletNode(wsAudioContext, "pcm-player");
    pcmNode.port.onmessage = (event) => {
        if (event.data && event.data.type === 'drained') {
            // Worklet buffer is empty — cancel drain timer and signal VAD to resume
            if (_drainTimer) {
                clearTimeout(_drainTimer);
                _drainTimer = null;
            }
            _onWorkletDrained();
        }
    };
    wsGainNode = wsAudioContext.createGain();
    wsGainNode.gain.value = 1.0;

    pcmNode.connect(wsGainNode);
    wsGainNode.connect(wsAudioContext.destination);

    if (wsAudioContext.state === "suspended") await wsAudioContext.resume();
    console.log("[WS-AUDIO] AudioWorklet initialized at", nativeSampleRate, "Hz");
}

// ============== PUSH AUDIO ==============
function pushAudioData(samples) {
    // Ignore audio arriving after stopAudio() - prevents late tts_audio frames
    // from resetting _pcmWorkletBufferEmpty and stalling the drain poller.
    if (!_audioGate) return;
    if (!pcmNode || !wsAudioContext || !samples || samples.length === 0) return;

    samples = upsample24toNative(samples);

    // Drop the backlog if the buffer has grown beyond the cap (~5 seconds).
    // This prevents a multi-second drain wait when TTS streams faster than playback.
    if (_workletSamplesQueued > MAX_BUFFER_SAMPLES) {
        console.warn(`[AUDIO] Buffer cap reached (${_workletSamplesQueued} samples), clearing backlog`);
        if (pcmNode && pcmNode.port) {
            pcmNode.port.postMessage({ type: 'reset' });
        }
        _workletSamplesQueued = 0;
        pendingBuffer = new Float32Array(0);
        startupBuffer = [];
        bufferedSamples = 0;
        playbackStarted = false;
        return;
    }

    if (!playbackStarted) {
        startupBuffer.push(samples);
        bufferedSamples += samples.length;

        if (bufferedSamples >= START_BUFFER_SAMPLES) {
            const merged = mergeFloat32Arrays(startupBuffer);
            appendSamples(merged);

            while (pendingBuffer.length >= FRAME_SIZE) {
                const frame = pendingBuffer.slice(0, FRAME_SIZE);
                pcmNode.port.postMessage(frame);
                _workletSamplesQueued += frame.length;
                pendingBuffer = pendingBuffer.slice(FRAME_SIZE);
            }

            const remainder = pendingBuffer;
            pendingBuffer = remainder;
            playbackStarted = true;
            startupBuffer = [];
            bufferedSamples = 0;
        }
        return;
    }

    appendSamples(samples);

    while (pendingBuffer.length >= FRAME_SIZE) {
        const frame = pendingBuffer.slice(0, FRAME_SIZE);
        pcmNode.port.postMessage(frame);
        _workletSamplesQueued += frame.length;
        pendingBuffer = pendingBuffer.slice(FRAME_SIZE);
    }
}

// ============== HANDLE INCOMING PCM ==============
function handleAudioData(pcmBytes) {
    // Backend sends raw 16-bit signed PCM (Int16). Re-interpreting the bytes
    // directly as Float32 would produce garbage noise; convert properly.
    // Handle odd-length buffers by zero-padding instead of dropping frames.
    let buffer = pcmBytes;
    if (buffer.byteLength % 2 !== 0) {
        const padded = new Uint8Array(buffer.byteLength + 1);
        padded.set(new Uint8Array(buffer));
        padded[buffer.byteLength] = 0;
        buffer = padded.buffer;
    }
    const int16 = new Int16Array(buffer);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
        float32[i] = int16[i] / 32768.0;
    }
    pushAudioData(float32);
}

// ============== STOP AUDIO ==============
function stopAudio() {
    // Signal stop for TTS streaming
    if (typeof stopAudioRequested !== 'undefined') {
        stopAudioRequested = true;
    }
    
    // Abort any ongoing TTS stream
    if (typeof window.currentStreamAbort === 'function') {
        window.currentStreamAbort();
    }
    
    // Stop TTS audio playback
    if (typeof window.stopTTSAudio === 'function') {
        window.stopTTSAudio();
    }
    
    // Do NOT flush startupBuffer or pendingBuffer here.
    // If 'done' arrives before all binary WebSocket frames have been received
    // (race condition), those buffers contain only partial audio and flushing
    // them causes replayed or corrupted audio. The worklet drains itself
    // naturally from whatever was already posted to it.
    if (pcmNode && pcmNode.port) {
        pcmNode.port.postMessage({ type: "stop" });
    }
    pendingBuffer = new Float32Array(0);
    playbackStarted = false;
    startupBuffer = [];
    bufferedSamples = 0;
    isSpeaking = false;
    _audioGate = false;  // block any tts_audio frames still in the socket buffer
    window.VoiceState.tokenBuffer = '';
    window.VoiceState.llmStreaming = false;
    
    // DO NOT set assistantSpeaking=false or trigger TTS cooldown here.
    // The worklet uses a soft-stop (draining mode) — it continues playing
    // all already-queued audio for several more seconds. If we mark the
    // assistant as done now, the VAD loop will pick up the AI's own voice
    // from the speakers and fire a spurious second LLM request.
    //
    // Instead, poll until the worklet has actually finished draining, then
    // signal the cooldown. We estimate drain time from audio context clock.
    _waitForWorkletDrain();
}


// Wait for PCM worklet drain then signal VAD to resume.
// The worklet posts a 'drained' message (set up in initAudioWorklet) when its
// buffer empties. We listen for that, with a hard 6s timeout as a safety net
// so the engine can never get permanently stuck.
let _drainTimer = null;
let _drainResolve = null;

function _waitForWorkletDrain() {
    // Cancel any in-flight drain wait
    if (_drainTimer) { clearTimeout(_drainTimer); _drainTimer = null; }
    _drainCalledThisTurn = false;

    if (!wsAudioContext || !pcmNode) {
        _onWorkletDrained();
        return;
    }

    // Compute how long the queued audio will take to play at the native sample rate,
    // then add a 3s margin. This is far more accurate than a fixed timeout and
    // avoids cutting off long responses prematurely.
    // Primary signal: worklet posts 'drained' when its buffer empties (fast path).
    // Fallback: this timer fires if the 'drained' message is somehow never received.
    const drainMs = Math.ceil((_workletSamplesQueued / (nativeSampleRate || 48000)) * 1000) + 3000;
    console.log(`[WS-AUDIO] Waiting for drain: ~${Math.ceil(drainMs/1000)}s (${_workletSamplesQueued} samples @ ${nativeSampleRate}Hz)`);

    _drainTimer = setTimeout(() => {
        console.warn('[WS-AUDIO] Drain timeout — forcing listening resume');
        _drainTimer = null;
        _onWorkletDrained();
    }, drainMs);
}

function _onWorkletDrained() {
    // Guard: only fire once per turn to prevent double-cooldown when both
    // the worklet message and the timeout fire (e.g. timeout fires first,
    // then worklet message arrives for a long response)
    if (_drainCalledThisTurn) return;
    _drainCalledThisTurn = true;

    if (_drainTimer) { clearTimeout(_drainTimer); _drainTimer = null; }

    window.VoiceState.assistantSpeaking = false;

    if (typeof window.triggerTTSCooldown === 'function') {
        window.triggerTTSCooldown();
    }

    // If always-listening mode is active, show the listening indicator so
    // the user knows the system is ready for their next voice turn.
    // Otherwise fall back to a generic "Ready to chat" idle state.
    const alwaysListeningBtn = document.getElementById('alwaysListeningBtn');
    const isAutoListening = alwaysListeningBtn && alwaysListeningBtn.classList.contains('active');

    if (typeof updateConversationStatus === 'function') {
        updateConversationStatus(
            isAutoListening ? '🎤 Auto-listening - Speak now!' : 'Ready to chat',
            isAutoListening ? 'listening' : ''
        );
    }
    if (typeof showCircleIndicator === 'function') {
        showCircleIndicator(isAutoListening ? 'listening' : 'idle');
    }
}

// ============== WEBSOCKET CONNECTION ==============
async function connectWebSocket(sessionIdVal, speakerVal) {
    wsSessionId = sessionIdVal;
    currentSpeaker = speakerVal;

    if (ws && isConnected) {
        // Validate the socket is truly OPEN before reusing it.
        if (ws.readyState !== WebSocket.OPEN) {
            console.log('[WS-CLIENT] Stale connection (readyState=' + ws.readyState + '), reconnecting');
            isConnected = false;
            ws = null;
        } else {
            console.log('[WS-CLIENT] Already connected, reusing connection');
            // Reset worklet and all playback state for the new turn.
            // Without this, playbackStarted stays true from the prior turn,
            // causing the pre-buffer to be skipped and audio to underrun immediately.
            if (pcmNode && pcmNode.port) {
                pcmNode.port.postMessage({ type: 'reset' });
            }
            playbackStarted = false;
            startupBuffer = [];
            bufferedSamples = 0;
            pendingBuffer = new Float32Array(0);
            ws.send(JSON.stringify({
                type: 'config',
                session_id: wsSessionId,
                speaker: currentSpeaker
            }));
            return Promise.resolve();
        }
    }

    if (pcmNode && pcmNode.port) {
        pcmNode.port.postMessage({ type: 'reset' });
    }
    playbackStarted = false;
    startupBuffer = [];
    bufferedSamples = 0;
    pendingBuffer = new Float32Array(0);

    await initAudioWorklet();

    // Capture socket in a local variable so closures below always reference the
    // correct instance even if `ws` is reassigned by a concurrent connection attempt.
    const socket = new WebSocket(WS_URL);
    socket.binaryType = "arraybuffer";
    ws = socket;

    socket.onopen = () => {
        // Guard against stale callbacks from a superseded connection attempt.
        if (ws !== socket) {
            if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
                socket.close();
            }
            return;
        }
        console.log("[WS-CLIENT] Connected");
        isConnected = true;
        socket.send(JSON.stringify({ type: "config", session_id: wsSessionId, speaker: currentSpeaker }));
        
        // Send any queued messages
        while (pendingMessages.length > 0) {
            const msg = pendingMessages.shift();
            if (msg.type === 'text') {
                addWSSystemMessage('user', msg.text);
                streamedContent = '';
                currentAssistantDiv = null;
                responseComplete = false;
                _audioGate = true;
                socket.send(JSON.stringify({ type: 'text', text: msg.text }));
            }
        }
    };

    socket.onmessage = async (event) => {
        if (event.data instanceof ArrayBuffer) {
            handleAudioData(event.data);
            return;
        }
        const msg = JSON.parse(event.data);
        handleMessage(msg);
    };

    socket.onerror = (err) => console.error("[WS-CLIENT] Error:", err);
    socket.onclose = () => {
        if (ws === socket) {
            console.log("[WS-CLIENT] Disconnected");
            isConnected = false;
            isSpeaking = false;
            // Make sure VAD can resume even if the socket drops mid-response
            if (window.VoiceState && window.VoiceState.assistantSpeaking) {
                stopAudio();
            }
        }
    };
}


/**
 * Handle incoming messages
 */
async function handleMessage(msg) {
    const type = msg.type;
    
    switch (type) {
        case 'ready':
            console.log('[WS-CLIENT] Ready for conversation');
            if (typeof updateConversationStatus === 'function') {
                updateConversationStatus('Ready to chat');
            }
            break;
            
        case 'token':
            if (llmFirstTokenTime === 0) {
                llmFirstTokenTime = msg.time;
                console.log(`🕐 [WS] LLM first token: ${msg.time}ms`);
            }
            break;
            
        case 'llm_token':
            window.VoiceState.tokenBuffer += msg.token;
            window.VoiceState.llmStreaming = true;
            
            streamedContent += msg.token;
            if (currentAssistantDiv) {
                const contentEl = currentAssistantDiv.querySelector('.conversation-message-content, .message-content, .message-text');
                if (contentEl) {
                    contentEl.textContent = streamedContent;
                } else {
                    currentAssistantDiv.textContent = streamedContent;
                }
            } else {
                currentAssistantDiv = addWSSystemMessage('assistant', streamedContent);
            }
            
            if (shouldEmitChunk(window.VoiceState.tokenBuffer)) {
                sendTextToTTS(window.VoiceState.tokenBuffer);
                window.VoiceState.tokenBuffer = "";
            }
            break;
            
        case 'tts_start':
            firstAudioTime = msg.time;
            console.log(`🕐 [WS] TTS first chunk: ${firstAudioTime}ms`);
            
            const tokensGeneratedTts = streamedContent ? Math.ceil(streamedContent.length / 4) : 0;
            const tokenSpeedTts = (llmFirstTokenTime > 0 && tokensGeneratedTts > 0) 
                ? (tokensGeneratedTts / (firstAudioTime / 1000)) 
                : 0;
            
            if (typeof window.updateTimingSummary === 'function') {
                window.updateTimingSummary({
                    requestStart: totalStartTime,
                    total: firstAudioTime,
                    llm: llmFirstTokenTime > 0 ? llmFirstTokenTime : 0,
                    llmDone: firstAudioTime,
                    tts: firstAudioTime,
                    audioPlayStart: firstAudioTime,
                    tokens: tokensGeneratedTts,
                    tokensPerSecond: tokenSpeedTts
                });
            }
            break;
            
        case 'content':
            streamedContent += msg.content;
            if (currentAssistantDiv) {
                const contentEl = currentAssistantDiv.querySelector('.conversation-message-content, .message-content, .message-text');
                if (contentEl) {
                    contentEl.textContent = streamedContent;
                } else {
                    currentAssistantDiv.textContent = streamedContent;
                }
            } else {
                currentAssistantDiv = addWSSystemMessage('assistant', streamedContent);
            }
            break;
            
        case 'audio':
            const audioBase64 = msg.data;
            if (!audioBase64) {
                console.warn('[WS-CLIENT] No audio data in message');
                break;
            }
            
            const audioBytes = atob(audioBase64);
            const wavBuffer = new ArrayBuffer(audioBytes.length);
            const wavUint8Array = new Uint8Array(wavBuffer);
            for (let i = 0; i < audioBytes.length; i++) {
                wavUint8Array[i] = audioBytes.charCodeAt(i);
            }
            
            if (typeof window.wsWavAudioContext === 'undefined') {
                window.wsWavAudioContext = new (window.AudioContext || window.webkitAudioContext)();
            }
            
            try {
                const audioBuffer = await window.wsWavAudioContext.decodeAudioData(wavBuffer.slice(0));
                const channelData = audioBuffer.getChannelData(0);
                
                if (!responseComplete && !isSpeaking) {
                    isSpeaking = true;
                    window.VoiceState.assistantSpeaking = true;
                    if (typeof updateConversationStatus === 'function') {
                        updateConversationStatus('🔊 Speaking...', 'speaking');
                    }
                    if (typeof showCircleIndicator === 'function') {
                        showCircleIndicator('speaking');
                    }
                }
                
                pushAudioData(channelData);
            } catch (e) {
                console.error('[WS-CLIENT] Failed to decode audio:', e);
            }
            break;
            
        case 'done':
            const totalTime = msg.total_time;
            console.log(` [WS] Total⏱️ response time: ${totalTime.toFixed(0)}ms`);
            
            responseComplete = true;
            window.VoiceState.llmStreaming = false;
            inFlightMessageId = null;  // release the single-flight guard
            
            if (window.VoiceState.tokenBuffer.length > 0) {
                sendTextToTTS(window.VoiceState.tokenBuffer);
                window.VoiceState.tokenBuffer = '';
            }
            
            // Do NOT manually flush pendingBuffer here. Binary WebSocket frames
            // and JSON control messages share the same socket but are processed
            // in order — however stopAudio() resets state immediately, so any
            // binary frames that arrive after 'done' (due to OS socket buffering)
            // would be pushed into a reset worklet and replayed. Let the server-side
            // TTS drain wait (asyncio.sleep + queue drain) guarantee all audio
            // has been sent before this message arrives.
            
            const tokensGeneratedDone = streamedContent ? Math.ceil(streamedContent.length / 4) : 0;
            const tokenSpeedDone = (llmFirstTokenTime > 0 && tokensGeneratedDone > 0) 
                ? (tokensGeneratedDone / (totalTime / 1000)) 
                : 0;
            
            if (typeof window.updateTimingSummary === 'function') {
                window.updateTimingSummary({
                    requestStart: totalStartTime,
                    total: totalTime,
                    llm: llmFirstTokenTime > 0 ? llmFirstTokenTime : 0,
                    llmDone: totalTime,
                    tts: firstAudioTime > 0 ? firstAudioTime : totalTime,
                    audioPlayStart: firstAudioTime > 0 ? firstAudioTime : totalTime,
                    tokens: tokensGeneratedDone,
                    tokensPerSecond: tokenSpeedDone
                });
            }
            
            stopAudio();
            
            if (typeof updateConversationStatus === 'function') {
                updateConversationStatus('Ready to chat');
            }
            
            // Re-enable the conversation send button so the user can type the
            // next message immediately after this turn completes.
            const convSendBtn = document.getElementById('conversationSendBtn');
            const convInput = document.getElementById('conversationInput');
            if (convSendBtn && convInput) {
                convSendBtn.disabled = !convInput.value.trim();
            }
            
            currentAssistantDiv = null;
            streamedContent = '';
            break;
            
        case 'stopped':
            inFlightMessageId = null;  // release the single-flight guard
            stopAudio();
            currentAssistantDiv = null;
            streamedContent = '';
            break;
            
        case 'error':
            console.error('[WS-CLIENT] Server error:', msg.error);
            inFlightMessageId = null;  // release the single-flight guard on error
            stopAudio();
            // Only trigger rate-limit cooldown for actual rate-limit errors,
            // not for empty/spurious error frames which just add unnecessary dead time
            if (msg.error && typeof window.triggerLLMCooldown === 'function') {
                window.triggerLLMCooldown();
            }
            if (typeof updateConversationStatus === 'function') {
                updateConversationStatus('Error: ' + msg.error);
            }
            break;
            
        case 'tts_audio':
            const pcmBase64 = msg.pcm;
            if (!pcmBase64) {
                console.warn('[WS-CLIENT] No PCM data in message');
                break;
            }
            
            const pcmBytes = atob(pcmBase64);
            const pcmBuffer = new ArrayBuffer(pcmBytes.length);
            const pcmUint8Array = new Uint8Array(pcmBuffer);
            for (let i = 0; i < pcmBytes.length; i++) {
                pcmUint8Array[i] = pcmBytes.charCodeAt(i);
            }
            
            const int16Array = new Int16Array(pcmBuffer);
            const float32Array = new Float32Array(int16Array.length);
            for (let i = 0; i < int16Array.length; i++) {
                float32Array[i] = int16Array[i] / 32768.0;
            }
            
            if (!responseComplete && !isSpeaking) {
                isSpeaking = true;
                window.VoiceState.assistantSpeaking = true;
                if (typeof updateConversationStatus === 'function') {
                    updateConversationStatus('🔊 Speaking...', 'speaking');
                }
                if (typeof showCircleIndicator === 'function') {
                    showCircleIndicator('speaking');
                }
            }
            
            pushAudioData(float32Array);
            break;
    }
}


// ============== API FUNCTIONS ==============
window.wsConversationStart = async function(sessionIdVal, speakerVal) {
    try {
        totalStartTime = performance.now();
        llmFirstTokenTime = 0;
        firstAudioTime = 0;
        _audioGate = true;
        
        // Clear any stale llmStreaming flag and in-flight guard left over from a
        // previous turn that ended via timeout or error rather than a clean 'done'
        // message.  This prevents the guards in wsConversationSend from incorrectly
        // blocking the very first send of a new turn.
        if (window.VoiceState) {
            window.VoiceState.llmStreaming = false;
        }
        inFlightMessageId = null;
        
        playbackStarted = false;
        startupBuffer = [];
        bufferedSamples = 0;
        
        await connectWebSocket(sessionIdVal, speakerVal);
        
        return { success: true };
    } catch (e) {
        console.error('[WS-CLIENT] Connection failed:', e);
        return { success: false, error: e.message };
    }
};


window.wsConversationSend = function(text) {
    // Single-flight guard: reject if a message is already being processed.
    if (inFlightMessageId) {
        console.warn('[WS-CLIENT] Message already in flight, dropping duplicate send');
        return false;
    }

    if (window.VoiceState.llmStreaming) {
        console.log('[WS-CLIENT] LLM already streaming, preventing request storm');
        return false;
    }

    // Generate a unique ID for this in-flight message.
    inFlightMessageId = (typeof crypto !== 'undefined' && crypto.randomUUID)
        ? crypto.randomUUID()
        : Date.now().toString() + '-' + Math.random().toString(36).substr(2, 9);
    
    if (!ws || !isConnected) {
        console.log('[WS-CLIENT] Queuing message, waiting for connection');
        pendingMessages.push({ type: 'text', text: text });
        // Return true: the message is queued and WILL be sent when the socket opens.
        // Returning true prevents callers from incorrectly falling back to HTTP.
        return true;
    }
    
    try {
        addWSSystemMessage('user', text);
        
        // Reset all per-turn state so each new response starts clean.
        // If playbackStarted is left true from the prior turn, incoming
        // audio skips the pre-buffer and hits the worklet before it has
        // enough data queued, causing an immediate underrun and cutoff.
        streamedContent = '';
        currentAssistantDiv = null;
        responseComplete = false;
        llmFirstTokenTime = 0;
        firstAudioTime = 0;
        totalStartTime = performance.now();
        playbackStarted = false;
        startupBuffer = [];
        bufferedSamples = 0;
        pendingBuffer = new Float32Array(0);
        isSpeaking = false;
        _audioGate = true;  // re-open for new turn
        _workletSamplesQueued = 0;
        _drainCalledThisTurn = false;
        window.VoiceState.tokenBuffer = '';
        
        ws.send(JSON.stringify({
            type: 'text',
            text: text
        }));
        
        window.VoiceState.llmStreaming = true;
        return true;
    } catch (e) {
        console.error('[WS-CLIENT] Send failed:', e);
        inFlightMessageId = null;  // clear guard so the next attempt can proceed
        return false;
    }
};


window.wsConversationStop = function() {
    if (!ws || !isConnected) {
        return;
    }
    
    try {
        ws.send(JSON.stringify({ type: 'stop' }));
        stopAudio();
    } catch (e) {
        console.error('[WS-CLIENT] Stop failed:', e);
    }
};


window.wsConversationDisconnect = function() {
    if (ws) {
        ws.close();
        ws = null;
    }
    isConnected = false;
    isSpeaking = false;
    inFlightMessageId = null;  // release the single-flight guard
    stopAudio();
};

function cancelLLMStream() {
    if (!ws) return;
    
    try {
        ws.send(JSON.stringify({
            type: "cancel_generation"
        }));
        
        window.VoiceState.llmStreaming = false;
        window.VoiceState.tokenBuffer = "";
        inFlightMessageId = null;  // release the single-flight guard
        
        console.log('[WS-CLIENT] LLM stream cancelled');
    } catch (e) {
        console.error('[WS-CLIENT] Cancel failed:', e);
    }
}

window.cancelLLMStream = cancelLLMStream;
window.stopAudio = stopAudio;

console.log('[WS-CLIENT] Loaded and ready');

} // end __WS_CLIENT_LOADED__ guard