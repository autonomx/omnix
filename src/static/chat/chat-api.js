/**
 * LM Studio Chatbot - Chat API
 * Handles sending messages and conversation REST API
 */

function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

async function generateSmartTitle(userMessage, aiResponse) {
    try {
        const response = await fetch('/api/sessions/generate-title', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_message: userMessage, ai_response: aiResponse })
        });
        const data = await response.json();
        if (data.success && data.title) return data.title;
    } catch (e) {
        console.error('Error generating title:', e);
    }
    return null;
}

// Singleton for Web Audio Context. 
// No sampleRate param passed to prevent locking the global context to an arbitrary rate.
function getAudioContext() {
    if (!window._globalAudioContext) {
        console.log('[TTS DEBUG] Creating new AudioContext');
        window._globalAudioContext = window.AudioPlayer?.getWebAudioContext?.() || new (window.AudioContext || window.webkitAudioContext)();
        console.log('[TTS DEBUG] AudioContext created:', { state: window._globalAudioContext.state, sampleRate: window._globalAudioContext.sampleRate });
    }
    return window._globalAudioContext;
}

async function sendMessage() {
    const message = messageInput.value.trim();
    const attachments = window.getAttachments ? window.getAttachments() :[];
    
    if ((!message && attachments.length === 0) || isLoading) return;
    
    welcomeMessage.classList.add('hidden');
    addMessage('user', message, null, null, '', attachments);
    
    messageInput.value = '';
    messageInput.style.height = 'auto';
    sendBtn.disabled = true;
    
    if (window.clearAttachments) window.clearAttachments();
    
    isLoading = true;
    statusDot.className = 'status-dot loading';
    statusText.textContent = 'Thinking...';
    typingIndicator.style.display = 'flex';
    
    const startTime = Date.now();
    if (window.features?.startTokenRateTracking) window.features.startTokenRateTracking();
    if (typeof window.TTSQueue?.clearAudioQueue === 'function') window.TTSQueue.clearAudioQueue();
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message ai';
    messageDiv.innerHTML = `
        <div class="message-header">
            <span class="message-label">AI</span>
            <span class="tts-playing" style="display: none;">🔊 Speaking...</span>
            <button class="speak-btn" title="Speak">Speak</button>
            <button class="pause-btn" title="Pause" style="display: none;">⏸</button>
            <button class="stop-btn" title="Stop" style="display: none;">⏹</button>
            <button class="copy-btn" title="Copy">Copy</button>
        </div>
        <div class="message-content streaming"></div>
    `;
    messagesContainer.appendChild(messageDiv);
    
    let chunks =[];
    let streamedContent = '';
    let thinkingContent = '';
    let audioChunkCount = 0;
    let directModeDone = false;
    let firstTokenTime = null;
    let contentEl = messageDiv.querySelector('.message-content');
    
    let scrollPending = false;
    const requestThrottledScroll = () => {
        if (!scrollPending) {
            scrollPending = true;
            requestAnimationFrame(() => {
                scrollToBottom();
                scrollPending = false;
            });
        }
    };
    
    // Never use direct mode for non-LMStudio providers
    const useDirectMode = document.getElementById('lmstudioDirect')?.checked && providerSelect?.value === 'lmstudio';
    const lmstudioBaseUrl = document.getElementById('lmstudioUrl')?.value || 'http://localhost:1234';
    const endpoint = useDirectMode ? `${lmstudioBaseUrl}/v1/chat/completions` : '/api/chat/stream';
    let isDirectLMStudio = useDirectMode;

    const attachMessageListeners = (container) => {
        container.querySelector('.copy-btn')?.addEventListener('click', (e) => copyToClipboard(streamedContent, e.target));
        
        container.querySelector('.stop-btn')?.addEventListener('click', () => {
            fetch('/api/tts/stream/cancel', { method: 'POST' }).catch(() => {});
            if (typeof window.stopTTSAudio === 'function') window.stopTTSAudio();
            setTTSButtonState(messageDiv, 'idle');
        });

        container.querySelector('.speak-btn')?.addEventListener('click', async () => {
            if (isPaused && currentMessageDiv === messageDiv) {
                isPaused = false;
                isPlaying = false; // Bypass the queue guard as requested
                playQueuedAudio(); // Guarantee pipeline restart
                setTTSButtonState(messageDiv, 'playing');
                return;
            }

            const speaker = document.getElementById('ttsSpeaker')?.value || 'en';
            const speakPromise = speakText(streamedContent, speaker);
            
            currentMessageDiv = messageDiv;
            setTTSButtonState(messageDiv, 'playing');

            try {
                await speakPromise;
            } catch (err) {
                console.error('[TTS] Speak error:', err);
                setTTSButtonState(messageDiv, 'idle');
            }
        });
    };

    attachMessageListeners(messageDiv);
    
    const handleChunk = (content) => {
        if (directModeDone) return; // Prevent stray chunks after completion
        chunks.push(content);
        if (!contentEl) contentEl = messageDiv.querySelector('.message-content');
        if (contentEl) contentEl.textContent += content;
        requestThrottledScroll();
    };

    const handleDone = async (thinking = '') => {
        if (directModeDone) return;
        directModeDone = true;
        
        streamedContent = chunks.join('');
        
        if (thinking) {
            thinkingContent = thinking;
        } else if (typeof extractThinkingFromContent === 'function') {
            const extracted = extractThinkingFromContent(streamedContent);
            if (extracted?.thinking) {
                thinkingContent = extracted.thinking;
                streamedContent = extracted.content;
            }
        }

        const generationTimeMs = startTime ? (Date.now() - startTime) : null;
        const tokensGenerated = streamedContent ? Math.ceil(streamedContent.length / 4) : 0;
        const tokenSpeed = generationTimeMs > 0 && tokensGenerated > 0 ? (tokensGenerated / (generationTimeMs / 1000)) : 0;

        const tokenUpdater = typeof window.updateTokenCounterFromText === 'function' ? window.updateTokenCounterFromText : window.features?.updateTokenCounterFromText;
        if (tokenUpdater) tokenUpdater(message, streamedContent, generationTimeMs);

        if (typeof window.updateTimingSummary === 'function') {
            window.updateTimingSummary({
                requestStart: startTime || performance.now(),
                total: generationTimeMs || 0,
                llm: firstTokenTime || generationTimeMs || 0,
                llmDone: generationTimeMs || 0,
                tts: 0,
                audioPlayStart: 0,
                tokens: tokensGenerated,
                tokensPerSecond: tokenSpeed
            });
        }

        messageDiv.innerHTML = '';

        if (thinkingContent) {
            const thinkingContainer = document.createElement('div');
            thinkingContainer.className = 'thinking-container collapsed';
            thinkingContainer.innerHTML = `
                <div class="thinking-header">
                    <span class="thinking-toggle">▶ Thinking</span>
                    <span class="thinking-label">(${thinkingContent.length} chars)</span>
                </div>
                <div class="thinking-content"></div>
            `;
            thinkingContainer.querySelector('.thinking-content').textContent = thinkingContent;
            thinkingContainer.querySelector('.thinking-header').addEventListener('click', () => {
                thinkingContainer.classList.toggle('collapsed');
                thinkingContainer.querySelector('.thinking-toggle').textContent = thinkingContainer.classList.contains('collapsed') ? '▶ Thinking' : '▼ Thinking';
            });
            messageDiv.appendChild(thinkingContainer);
        }

        const headerDiv = document.createElement('div');
        headerDiv.className = 'message-header';
        headerDiv.innerHTML = `
            <span class="message-label">AI</span>
            ${audioChunkCount > 0 ? '<span class="tts-playing" style="display: none;">🔊 Speaking...</span>' : ''}
            <button class="speak-btn" title="Speak">Speak</button>
            <button class="pause-btn" title="Pause" style="display: none;">⏸</button>
            <button class="stop-btn" title="Stop" style="display: none;">⏹</button>
            <button class="copy-btn" title="Copy">Copy</button>
        `;
        
        attachMessageListeners(headerDiv);
        messageDiv.appendChild(headerDiv);

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        if (typeof renderMarkdown === 'function') {
            const rawHtml = renderMarkdown(streamedContent);
            contentDiv.innerHTML = typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(rawHtml) : rawHtml;
        } else {
            contentDiv.textContent = streamedContent;
        }
        
        messageDiv.appendChild(contentDiv);
        
        if (currentMessageDiv === messageDiv) {
            setTTSButtonState(messageDiv, isPaused ? 'paused' : (isPlaying ? 'playing' : 'idle'));
        }
        
        scrollToBottom();
        
        if (typeof conversationMode !== 'undefined' && conversationMode && streamedContent && !isDirectLMStudio) {
            await speakText(streamedContent, document.getElementById('ttsSpeaker')?.value || 'en');
        }
    };

    try {
        let systemPrompt = systemPromptInput?.value || 'You are a helpful AI assistant.';
        const ttsSpeakerSelect = document.getElementById('ttsSpeaker');
        
        if (ttsSpeakerSelect?.value && window.features) {
            const voiceProfile = window.features.getVoiceProfile(ttsSpeakerSelect.value);
            if (voiceProfile?.personality && !systemPrompt.includes(voiceProfile.name)) {
                systemPrompt = `${systemPrompt}\n\n## Current Character: ${voiceProfile.name}\n${voiceProfile.personality}`;
            }
        }
        
        let processedAttachments = [];
        for (const file of attachments ||[]) {
            const isImage = file.type?.startsWith('image/') || /\.(png|jpe?g|gif|webp|bmp)$/i.test(file.name);
            processedAttachments.push({
                type: isImage ? 'image' : 'document',
                name: file.name,
                mimeType: file.type,
                ...(isImage && { data: await fileToBase64(file) })
            });
        }

        let fetchBody;
        if (useDirectMode) {
            const messages = systemPrompt ?[{ role: 'system', content: systemPrompt }] :[];
            const imageAttachments = processedAttachments.filter(a => a.type === 'image');
            
            if (imageAttachments.length > 0) {
                const contentParts = message ?[{ type: 'text', text: message }] :[];
                imageAttachments.forEach(img => contentParts.push({ type: 'image_url', image_url: { url: img.data } }));
                messages.push({ role: 'user', content: contentParts });
            } else {
                messages.push({ role: 'user', content: message });
            }
            fetchBody = JSON.stringify({ model: modelSelect.value, messages, stream: true });
        } else {
            const reqObj = { message, session_id: SessionManager?.sessionId, model: modelSelect.value, system_prompt: systemPrompt, attachments: processedAttachments };
            if (ttsSpeakerSelect?.value) reqObj.speaker = ttsSpeakerSelect.value;
            fetchBody = JSON.stringify(reqObj);
        }
        
        const response = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: fetchBody });
        if (!response.ok) throw new Error(`HTTP error: ${response.status}`);
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let sseBuffer = '';
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            sseBuffer += decoder.decode(value, { stream: true });
            const events = sseBuffer.split(/\r?\n\r?\n/);
            sseBuffer = events.pop() || '';
            
            for (const event of events) {
                const lines = event.split(/\r?\n/);
                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    const dataStr = line.slice(6);
                    if (dataStr.trim() === '') continue;
                    
                    if (dataStr === '[DONE]') {
                        if (isDirectLMStudio) await handleDone();
                        continue;
                    }
                    
                    try {
                        const data = JSON.parse(dataStr);
                        
                        if (isDirectLMStudio && data.choices?.[0]) {
                            if (data.choices[0].delta?.content) {
                                if (firstTokenTime === null) firstTokenTime = Date.now() - startTime;
                                handleChunk(data.choices[0].delta.content);
                            }
                            if (data.choices[0].finish_reason === 'stop') await handleDone();
                            continue;
                        }
                        
                        if (data.type === 'content') {
                            handleChunk(data.content);
                        } else if (data.type === 'audio') {
                            // Uses global window.TTSQueue built for chat SSE Integration
                            window.TTSQueue?.enqueueAudio?.(data.audio, data.sample_rate);
                            audioChunkCount++;
                            const ttsIndicator = messageDiv.querySelector('.tts-playing');
                            if (ttsIndicator) ttsIndicator.style.display = 'inline-flex';
                            window.TTSQueue?.playNextAudio?.();
                        } else if (data.type === 'done') {
                            await handleDone(data.thinking);
                        } else if (data.type === 'error') {
                            const errorEl = messageDiv.querySelector('.message-content');
                            if (errorEl) errorEl.innerHTML = `<span class="error">${data.error || 'An error occurred'}</span>`;
                        }
                    } catch (e) {
                        console.error('Error parsing SSE:', e);
                    }
                }
            }
        }
    } catch (error) {
        console.error('Error:', error);
        const errContentEl = messageDiv.querySelector('.message-content');
        if (errContentEl) errContentEl.innerHTML = '<span class="error">Failed to connect to the server</span>';
    } finally {
        isLoading = false;
        typingIndicator.style.display = 'none';
        checkHealth();
        
        // Strictly verified session bounds to prevent Title race conditions
        const safeSessionId = SessionManager?.sessionId;
        streamedContent = chunks.join('');
        
        if (safeSessionId && message && streamedContent) {
            if (SessionManager?.sessionId === safeSessionId) {
                const currentSession = window.sessions?.find(s => s.id === safeSessionId);
                if (currentSession && (currentSession.title === 'New Chat' || !currentSession.title)) {
                    const smartTitle = await generateSmartTitle(message, streamedContent);
                    if (smartTitle && SessionManager?.sessionId === safeSessionId) {
                        SessionManager.updateSessionTitle(safeSessionId, smartTitle);
                    }
                }
            }
        }
        window.SessionManager?.renderSessionList?.();
    }
}

async function speakText(text, speaker = 'en') {
    if (!text) return;
    
    if (typeof stopAudioRequested !== 'undefined') stopAudioRequested = false;
    if (typeof resetCrossfadeState === 'function') resetCrossfadeState();
    
    if (typeof conversationMode !== 'undefined' && conversationMode) {
        if(typeof micBtn !== 'undefined') micBtn.disabled = true;
        if(typeof conversationStatus !== 'undefined') conversationStatus.textContent = '🔊 Speaking...';
    }
    
    try {
        await speakTextStreaming(text, speaker);
    } catch (error) {
        console.error('[TTS] SSE streaming failed:', error);
        try {
            const batchResponse = await fetch('/api/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text, speaker })
            });
            const data = await batchResponse.json();
            if (data.success && data.audio && window.AudioPlayer?.playTTS) {
                await window.AudioPlayer.playTTS(data.audio);
            }
        } catch (batchError) {
            console.error('[TTS] Fallback failed:', batchError);
        }
    } finally {
        if (typeof conversationMode !== 'undefined' && conversationMode) {
            if(typeof micBtn !== 'undefined') micBtn.disabled = false;
            if(typeof conversationStatus !== 'undefined') conversationStatus.textContent = '🎙️ Voice Mode Active';
        }
    }
}

// Local playback variables tailored for speakTextStreaming (Distinct from global chat window.TTSQueue)
let currentStreamController = null;
let audioQueue =[]; 
let isPlaying = false;
let currentAudioSource = null;
let isPaused = false;
let currentMessageDiv = null;
let isFetching = false;

function setTTSButtonState(messageDiv, state) {
    if (!messageDiv) return;
    
    const speakBtn = messageDiv.querySelector('.speak-btn');
    const stopBtn = messageDiv.querySelector('.stop-btn');
    const pauseBtn = messageDiv.querySelector('.pause-btn');

    if (!speakBtn && !stopBtn && !pauseBtn) {
        console.log('[TTS] No TTS buttons found in messageDiv');
        return;
    }

    if (speakBtn) {
        speakBtn.style.display = (state === 'idle' || state === 'paused') ? 'inline-flex' : 'none';
        speakBtn.textContent = state === 'paused' ? 'Resume' : 'Speak';
        speakBtn.disabled = false;
    }
    
    if (stopBtn) {
        stopBtn.style.display = (state === 'playing' || state === 'paused') ? 'inline-flex' : 'none';
    }
    
    if (pauseBtn) {
        pauseBtn.style.display = state === 'playing' ? 'inline-flex' : 'none';
        if (pauseBtn) pauseBtn.textContent = '⏸';
    }
}

function onAudioPlaybackComplete() {
  console.log('[TTS DEBUG] onAudioPlaybackComplete CALLED');
  if (currentMessageDiv) {
    console.log('[TTS DEBUG] Resetting TTS button state to idle');
    setTTSButtonState(currentMessageDiv, 'idle');
    currentMessageDiv = null;
  }
  if (typeof triggerTTSCooldown === 'function') {
    console.log('[TTS DEBUG] Triggering TTS cooldown');
    triggerTTSCooldown();
  }
  console.log('[TTS DEBUG] ========== AUDIO PLAYBACK COMPLETE ==========');
}

function base64ToFloat32(b64) {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  
  const alignedLength = bytes.length - (bytes.length % 2);
  const int16 = new Int16Array(bytes.buffer.slice(0, alignedLength));
  
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768.0;
  return float32;
}

function scheduleChunk(float32Array, sampleRate) {
  console.log('[TTS DEBUG] scheduleChunk called with', float32Array.length, 'samples, sampleRate:', sampleRate);
  const audioCtx = getAudioContext();
  console.log('[TTS DEBUG] AudioContext state:', audioCtx?.state);
  
  // Start-click suppression:
  // 1) estimate and remove tiny DC offset from the opening window
  // 2) apply a short sample-domain fade-in over the first few milliseconds
  //
  // This is more reliable than only zeroing sample[0], because the PCM itself
  // may begin with a hard edge even if playback starts through a gain node.
  if (float32Array && float32Array.length > 0) {
    const dcWindow = Math.min(float32Array.length, Math.max(32, Math.floor(sampleRate * 0.005))); // ~5ms
    let dcSum = 0.0;
    for (let i = 0; i < dcWindow; i++) {
      dcSum += float32Array[i];
    }
    const dcOffset = dcWindow > 0 ? (dcSum / dcWindow) : 0.0;

    if (Math.abs(dcOffset) > 1e-6) {
      for (let i = 0; i < float32Array.length; i++) {
        float32Array[i] -= dcOffset;
      }
    }

    const fadeSamples = Math.min(float32Array.length, Math.max(64, Math.floor(sampleRate * 0.010))); // ~10ms
    for (let i = 0; i < fadeSamples; i++) {
      const t = i / fadeSamples;
      float32Array[i] *= t;
    }

    // Force exact silence at the first sample.
    float32Array[0] = 0.0;

    console.log('[TTS DEBUG] Applied input fade-in and DC offset correction', {
      dcOffset,
      fadeSamples
    });
  }

  const buffer = audioCtx.createBuffer(1, float32Array.length, sampleRate);
  buffer.copyToChannel(float32Array, 0);
  audioQueue.push(buffer);
  console.log('[TTS DEBUG] Buffer created and pushed to queue, new queue length:', audioQueue.length);
  
  // Auto-start playback as soon as the first chunk is available.
  // Some providers return a single large chunk, so waiting for 3 chunks deadlocks playback.
  if (!isPlaying && audioQueue.length > 0) {
    console.log('[TTS DEBUG] Auto-starting playback from scheduleChunk');
    playQueuedAudio();
  } else {
    console.log('[TTS DEBUG] Not auto-starting playback:', { isPlaying, queueLength: audioQueue.length });
  }
}

function playQueuedAudio() {
  console.log('[TTS DEBUG] playQueuedAudio CALLED');
  console.log('[TTS DEBUG] State check:', { isPlaying, isPaused, queueLength: audioQueue.length, hasCurrentSource: !!currentAudioSource });
  
  if (isPlaying && !isPaused) {
    console.log('[TTS DEBUG] Already playing and not paused, returning early');
    return; // Prevent dual-playing queue shifts
  }
  
  if (audioQueue.length === 0) {
    console.log('[TTS DEBUG] Audio queue empty, marking playback complete');
    isPlaying = false;
    currentAudioSource = null;
    onAudioPlaybackComplete();
    return;
  }
  
  ensureAudioContext();
  
  // Guard to ensure we don't accidentally shift a new buffer if one is currently paused/playing
  if (currentAudioSource) {
      console.log('[TTS DEBUG] Current audio source exists, returning early');
      isPlaying = true; 
      return; 
  }
  console.log('[TTS DEBUG] No current audio source, proceeding with queued playback');
  
  isPlaying = true;
  isPaused = false;
  console.log('[TTS DEBUG] Starting playback, queue length before shift:', audioQueue.length);
  
  const buffer = audioQueue.shift();
  console.log('[TTS DEBUG] Shifted buffer from queue:', { length: buffer.length, duration: buffer.duration.toFixed(3) + 's', sampleRate: buffer.sampleRate });
  
  const audioCtx = getAudioContext();
  console.log('[TTS DEBUG] AudioContext state before playback:', audioCtx?.state, 'currentTime:', audioCtx?.currentTime);
  
  const source = audioCtx.createBufferSource();
  source.buffer = buffer;
  
  // Keep a small output ramp in addition to the input fade-in.
  const gainNode = audioCtx.createGain();
  const now = audioCtx.currentTime;
  const startAt = now + 0.002;
  const fadeInSec = 0.005;

  gainNode.gain.cancelScheduledValues(now);
  gainNode.gain.setValueAtTime(0.0, now);
  gainNode.gain.linearRampToValueAtTime(1.0, startAt + fadeInSec);

  source.connect(gainNode);
  gainNode.connect(audioCtx.destination);
  currentAudioSource = source;
  console.log('[TTS DEBUG] Source created, connected through output ramp, set as currentAudioSource', {
    startAt,
    fadeInSec
  });
  
  source.onended = () => {
    console.log('[TTS DEBUG] Source onended event fired');
    isPlaying = false;
    currentAudioSource = null;
    if (!isPaused) {
      console.log('[TTS DEBUG] Not paused, calling playQueuedAudio again for next buffer');
      playQueuedAudio();
    } else {
      console.log('[TTS DEBUG] Paused, not playing next buffer');
    }
  };
  
  console.log('[TTS DEBUG] Calling source.start() with ramped start time');
  source.start(startAt);
  console.log('[TTS DEBUG] source.start() completed');
}

function stopTTSAudio() {
  if (currentStreamController) {
      currentStreamController.abort();
      currentStreamController = null;
  }
  if (currentAudioSource) {
    try { 
        currentAudioSource.stop();
        currentAudioSource.disconnect();
    } catch (e) {}
    currentAudioSource = null;
  }
  audioQueue =[];
  isPlaying = false;
  isPaused = false;
  isFetching = false;

  if (currentMessageDiv) {
      setTTSButtonState(currentMessageDiv, 'idle');
      currentMessageDiv = null;
  }
}

function pauseTTSAudio() {
  try {
    const audioCtx = getAudioContext();
    if (audioCtx?.state === 'running') audioCtx.suspend();
  } catch (e) { console.warn('[TTS] pause error', e); }
  
  isPaused = true; 
}

window.stopTTSAudio = stopTTSAudio;
window.pauseTTSAudio = pauseTTSAudio;
window.setTTSButtonState = setTTSButtonState;
window.isPlaying = isPlaying;
window.isPaused = isPaused;
window.audioQueue = audioQueue;

function ensureAudioContext() {
  console.log('[TTS DEBUG] ensureAudioContext called');
  try {
    const audioCtx = getAudioContext();
    console.log('[TTS DEBUG] AudioContext state check:', audioCtx?.state);
    if (audioCtx?.state === 'suspended') {
      console.log('[TTS DEBUG] AudioContext is suspended, calling resume()');
      audioCtx.resume().then(() => {
        console.log('[TTS DEBUG] AudioContext resumed successfully, new state:', audioCtx.state);
      }).catch(e => {
        console.error('[TTS DEBUG] Failed to resume AudioContext:', e);
      });
    }
  } catch (e) { console.warn('[TTS] Failed to resume AudioContext', e); }
}

window.testTTSControls = function() {
    console.log('=== TTS CONTROLS TEST ===\nTesting stops/pauses', {isPlaying, isPaused, length: audioQueue.length});
    stopTTSAudio();
    pauseTTSAudio();
    ensureAudioContext();
    return { isPlaying, isPaused, audioQueueLength: audioQueue.length };
};

async function speakTextStreaming(text, speaker = 'en') {
  console.log('[TTS DEBUG] speakTextStreaming CALLED with text:', text.substring(0, 50) + '..., speaker:', speaker);
  stopTTSAudio();
  if (isFetching) {
    console.log('[TTS DEBUG] Already fetching, returning early');
    return;
  }
  
  isFetching = true;
  console.log('[TTS DEBUG] Starting new stream request');
  
  return new Promise((resolve, reject) => {
    if (currentStreamController) {
      console.log('[TTS DEBUG] Aborting existing stream controller');
      currentStreamController.abort();
    }
    currentStreamController = new AbortController();
    
    const formData = new FormData();
    formData.append('text', text);
    formData.append('speaker', speaker || 'default');
    formData.append('language', 'en');
    console.log('[TTS DEBUG] Form data prepared:', { textLength: text.length, speaker: speaker || 'default', language: 'en' });
    
    window.currentStreamAbort = () => { if (currentStreamController) currentStreamController.abort(); };
    
    console.log('[TTS DEBUG] Sending POST request to /api/tts/stream/server-sent-events');
    fetch('/api/tts/stream/server-sent-events', {
      method: 'POST',
      body: formData,
      signal: currentStreamController.signal
    }).then(async response => {
      console.log('[TTS DEBUG] Response received:', { status: response.status, statusText: response.statusText, ok: response.ok });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let chunkCount = 0;
      console.log('[TTS DEBUG] Response body reader created, starting read loop');
      
      while (true) {
        if (typeof stopAudioRequested !== 'undefined' && stopAudioRequested) {
          console.log('[TTS DEBUG] Stop audio requested, cancelling reader');
          reader.cancel();
          currentStreamController.abort();
          resolve();
          return;
        }
        
        const { done, value } = await reader.read();
        console.log('[TTS DEBUG] Reader read result:', { done, valueLength: value ? value.length : 0 });
        
        if (done) {
          console.log('[TTS DEBUG] Read loop completed (done=true)');
          break;
        }
        
        buffer += decoder.decode(value, { stream: true });
        console.log('[TTS DEBUG] Buffer updated, new length:', buffer.length);
        
        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop();
        console.log('[TTS DEBUG] Parsed lines:', lines.length, 'lines, remaining buffer:', buffer.length);
        
        for (const line of lines) {
          console.log('[TTS DEBUG] Processing line:', line.substring(0, 100));
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              console.log('[TTS DEBUG] Parsed data:', { type: data.type, hasAudio: !!data.audio_b64, sampleRate: data.sample_rate });
              
              if (data.type === 'chunk') {
                chunkCount++;
                console.log('[TTS DEBUG] CHUNK RECEIVED #' + chunkCount + ', audio_b64 length:', data.audio_b64.length);
                
                const float32Data = base64ToFloat32(data.audio_b64);
                console.log('[TTS DEBUG] Decoded float32 data length:', float32Data.length, 'samples, duration:', (float32Data.length / data.sample_rate).toFixed(3) + 's');
                
                scheduleChunk(float32Data, data.sample_rate);
                console.log('[TTS DEBUG] Chunk scheduled, audioQueue length now:', audioQueue.length);
                
                // Start playback immediately once any audio has been queued.
                // This avoids hanging forever when the server emits only one chunk.
                if (!isPlaying && audioQueue.length > 0) {
                  console.log('[TTS DEBUG] Audio available, calling playQueuedAudio()');
                  playQueuedAudio();
                } else {
                  console.log('[TTS DEBUG] Not starting playback yet:', { isPlaying, audioQueueLength: audioQueue.length });
                }
              } else if (data.type === 'done') {
                console.log('[TTS DEBUG] DONE message received from server, total chunks:', chunkCount);
                // If audio was queued but playback never started yet, start it now.
                if (!isPlaying && audioQueue.length > 0) {
                  console.log('[TTS DEBUG] DONE received with queued audio and idle playback, forcing playQueuedAudio()');
                  playQueuedAudio();
                }

                // Wait for queue to finish before resolving
                const waitForQueue = () => {
                  if (audioQueue.length > 0 || isPlaying) {
                    console.log('[TTS DEBUG] Waiting for queue to finish:', { audioQueueLength: audioQueue.length, isPlaying });
                    setTimeout(waitForQueue, 100);
                  } else {
                    console.log('[TTS DEBUG] Playback complete, resolving promise');
                    resolve();
                  }
                };
                waitForQueue();
                return;
              } else if (data.type === 'error') {
                console.error('[TTS DEBUG] Error from server:', data.message);
                reject(new Error(data.message));
              }
            } catch (e) { console.error('[TTS] Parse error:', e, 'Line:', line); }
          }
        }
      }
    }).catch(err => {
      console.error('[TTS DEBUG] Fetch error:', err.name, err.message);
      if (err.name !== 'AbortError') reject(err);
    }).finally(() => {
      console.log('[TTS DEBUG] Request completed, cleaning up');
      currentStreamController = null;
      isFetching = false;
    });
  });
}

async function speakTextLegacy(text, speaker = 'en') {
  return new Promise((resolve, reject) => {
    let audioQueue =[];
    let isPlaying = false;
    
    async function playNextAudio() {
      if (isPlaying || audioQueue.length === 0) return;
      isPlaying = true;
      while (audioQueue.length > 0) {
        const { audio, sampleRate } = audioQueue.shift();
        try {
          if (window.AudioPlayer?.playTTS) await window.AudioPlayer.playTTS(audio, sampleRate);
        } catch (e) { console.error('[TTS] Playback error:', e); }
      }
      isPlaying = false;
    }
    
    fetch('/api/tts/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, speaker })
    }).then(response => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const reader = response.body.getReader();
      return new Promise((resolveLegacy, rejectLegacy) => {
        function processStream() {
          reader.read().then(({ done, value }) => {
            if (done) return resolveLegacy();
            let binary = '';
            for (let i = 0; i < value.length; i++) binary += String.fromCharCode(value[i]);
            audioQueue.push({ audio: btoa(binary), sampleRate: 24000 });
            playNextAudio();
            processStream();
          }).catch(rejectLegacy);
        }
        processStream();
      });
    }).then(() => {
      return new Promise(resolveWait => {
        const checkComplete = () => (isPlaying || audioQueue.length > 0) ? setTimeout(checkComplete, 100) : resolveWait();
        checkComplete();
      });
    }).then(resolve).catch(reject);
  });
}

async function clearChat() {
    messagesContainer.innerHTML = '';
    welcomeMessage.classList.remove('hidden');
    try {
        await fetch('/api/clear', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: SessionManager?.sessionId })
        });
    } catch (error) { console.error('Error clearing session:', error); }
    messageInput.focus();
}

async function loadSystemPrompt() {
    if (!SessionManager?.sessionId) return;
    try {
        const response = await fetch(`/api/sessions/${SessionManager.sessionId}`);
        const data = await response.json();
        systemPromptInput.value = (data.success && data.session.system_prompt) ? data.session.system_prompt : 'You are a helpful AI assistant.';
    } catch (error) { systemPromptInput.value = 'You are a helpful AI assistant.'; }
}

async function saveSystemPromptHandler() {
    try {
        await fetch(`/api/sessions/${SessionManager?.sessionId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                system_prompt: systemPromptInput.value,
                global_system_prompt: typeof globalSystemPromptInput !== 'undefined' ? globalSystemPromptInput?.value : ''
            })
        });
    } catch (error) { console.error('Error saving system prompt:', error); }
}

window.ChatAPI = { sendMessage, speakText, speakTextStreaming, speakTextLegacy, clearChat, loadSystemPrompt, saveSystemPromptHandler };

document.addEventListener('click', function(e) {
    if (e.target.classList.contains('pause-btn')) {
        const messageDiv = e.target.closest('.message');
        if (typeof window.pauseTTSAudio === 'function') window.pauseTTSAudio();
        setTTSButtonState(messageDiv, 'paused');
    }
});