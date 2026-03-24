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
        window._globalAudioContext = window.AudioPlayer?.getWebAudioContext?.() || new (window.AudioContext || window.webkitAudioContext)();
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
    
    const useDirectMode = document.getElementById('lmstudioDirect')?.checked;
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
  isPlaying = false;
  isPaused = false;
  if (currentMessageDiv) {
    setTTSButtonState(currentMessageDiv, 'idle');
    currentMessageDiv = null;
  }
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
  const audioCtx = getAudioContext();
  const buffer = audioCtx.createBuffer(1, float32Array.length, sampleRate);
  buffer.copyToChannel(float32Array, 0);
  audioQueue.push(buffer);
  
  // Auto-start playback if not playing and we have enough buffered (3+ chunks for smoothness)
  if (!isPlaying && audioQueue.length >= 3) {
    playQueuedAudio();
  }
}

function playQueuedAudio() {
  if (isPlaying && !isPaused) return; // Prevent dual-playing queue shifts
  
  if (audioQueue.length === 0) {
    isPlaying = false;
    currentAudioSource = null;
    onAudioPlaybackComplete();
    return;
  }
  
  ensureAudioContext();
  
  // Guard to ensure we don't accidentally shift a new buffer if one is currently paused/playing
  if (currentAudioSource) {
      isPlaying = true; 
      return; 
  }
  
  isPlaying = true;
  isPaused = false;
  
  const buffer = audioQueue.shift();
  const audioCtx = getAudioContext();
  
  const source = audioCtx.createBufferSource();
  source.buffer = buffer;
  source.connect(audioCtx.destination);
  currentAudioSource = source;
  
  source.onended = () => {
    isPlaying = false;
    currentAudioSource = null;
    if (!isPaused) playQueuedAudio();
  };
  
  source.start();
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

function ensureAudioContext() {
  try {
    const audioCtx = getAudioContext();
    if (audioCtx?.state === 'suspended') audioCtx.resume();
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
  stopTTSAudio();
  if (isFetching) return;
  
  isFetching = true;
  return new Promise((resolve, reject) => {
    if (currentStreamController) currentStreamController.abort();
    currentStreamController = new AbortController();
    
    const formData = new FormData();
    formData.append('text', text);
    formData.append('speaker', speaker || 'default');
    formData.append('language', 'en');
    
    window.currentStreamAbort = () => { if (currentStreamController) currentStreamController.abort(); };
    
    fetch('/api/tts/stream/server-sent-events', {
      method: 'POST',
      body: formData,
      signal: currentStreamController.signal
    }).then(async response => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      
      while (true) {
        if (typeof stopAudioRequested !== 'undefined' && stopAudioRequested) {
          reader.cancel();
          currentStreamController.abort();
          resolve();
          return;
        }
        
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop();
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === 'chunk') {
                scheduleChunk(base64ToFloat32(data.audio_b64), data.sample_rate);
                // Start playback only after buffering 3 chunks for smoother audio
                if (!isPlaying && audioQueue.length >= 3) {
                  playQueuedAudio();
                }
              } else if (data.type === 'done') {
                // Wait for queue to finish before resolving
                const waitForQueue = () => {
                  if (audioQueue.length > 0 || isPlaying) {
                    setTimeout(waitForQueue, 100);
                  } else {
                    resolve();
                  }
                };
                waitForQueue();
                return;
              } else if (data.type === 'error') {
                reject(new Error(data.message));
              }
            } catch (e) { console.error('[TTS] Parse error:', e); }
          }
        }
      }
    }).catch(err => {
      if (err.name !== 'AbortError') reject(err);
    }).finally(() => {
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