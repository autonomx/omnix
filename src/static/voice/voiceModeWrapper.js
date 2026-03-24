import { VoiceEngine, VoiceState } from './voiceEngine.js?v=5';

let voiceEngine = null;
let voiceModeActive = false;
let newVoiceModeInitialized = false;
let alwaysListening = true;

const VAD_SILENCE_THRESHOLD = 0.008;
const VAD_SILENCE_TIMEOUT = 400;
const MIN_SPEECH_DURATION = 0.3;

export function initNewVoiceMode() {
  if (newVoiceModeInitialized) return;
  newVoiceModeInitialized = true;
  
  const conversationToggle = document.getElementById('conversationToggle');
  const exitConversationBtn = document.getElementById('exitConversationBtn');
  const toggleMessagesBtn = document.getElementById('toggleMessagesBtn');
  const alwaysListeningBtn = document.getElementById('alwaysListeningBtn');
  
  if (!conversationToggle) {
    console.warn('[NewVoiceMode] conversationToggle not found');
    return;
  }

  conversationToggle.addEventListener('click', async (e) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (!voiceModeActive) {
      window.useNewVoiceMode = true;
      await startNewVoiceMode();
    } else {
      await stopNewVoiceMode();
      window.useNewVoiceMode = false;
    }
  });

  if (exitConversationBtn) {
    exitConversationBtn.addEventListener('click', async () => {
      await stopNewVoiceMode();
    });
  }

  if (toggleMessagesBtn) {
    toggleMessagesBtn.addEventListener('click', () => {
      const conversationMessages = document.getElementById('conversationMessages');
      if (!conversationMessages) return;
      const nowHidden = conversationMessages.classList.toggle('hidden');
      const label = toggleMessagesBtn.querySelector('span');
      if (label) {
        label.textContent = nowHidden ? 'Show Messages' : 'Messages';
      }
    });
  }

  const conversationInput = document.getElementById('conversationInput');
  const conversationSendBtn = document.getElementById('conversationSendBtn');

  if (conversationInput) {
    // Enable/disable send button based on input content
    conversationInput.addEventListener('input', () => {
      if (conversationSendBtn) {
        conversationSendBtn.disabled = !conversationInput.value.trim();
      }
    });

    // Submit on Enter (without Shift)
    conversationInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        submitConversationInput();
      }
    });
  }

  if (alwaysListeningBtn) {
    alwaysListeningBtn.addEventListener('click', toggleAlwaysListening);
  }

  if (conversationSendBtn) {
    conversationSendBtn.addEventListener('click', () => {
      submitConversationInput();
    });
  }
}

async function startNewVoiceMode() {
  if (voiceModeActive && voiceEngine) {
    return;
  }

  console.log('[NewVoiceMode] Starting...');
  voiceModeActive = true;

  const conversationToggle = document.getElementById('conversationToggle');
  const conversationStatusMessage = document.getElementById('conversationStatusMessage');
  const circleIndicator = document.getElementById('circleIndicator');
  const conversationChatView = document.getElementById('conversationChatView');
  const chatContainer = document.getElementById('chatContainer');
  const inputArea = document.querySelector('.input-area');

  if (chatContainer) {
    chatContainer.style.display = 'none';
  }

  if (inputArea) {
    inputArea.style.display = 'none';
  }

  if (conversationToggle) {
    conversationToggle.classList.add('active');
  }

  if (conversationChatView) {
    conversationChatView.classList.add('active');
  }

  if (circleIndicator) {
    circleIndicator.classList.add('active');
    const innerCircle = circleIndicator.querySelector('.circle-indicator');
    if (innerCircle) {
      innerCircle.classList.remove('idle', 'listening', 'speaking');
      innerCircle.classList.add('listening');
    }
  }

  if (conversationStatusMessage) {
    conversationStatusMessage.style.display = 'inline-block';
    conversationStatusMessage.textContent = 'Starting...';
    conversationStatusMessage.className = 'conversation-status-message listening';
  }

  const ttsSpeaker = document.getElementById('ttsSpeaker');
  const speaker = ttsSpeaker ? ttsSpeaker.value : 'default';

  voiceEngine = new VoiceEngine({
    speaker: speaker,
    sessionId: window.sessionId || null,
    alwaysListening: alwaysListening,
    onStateChange: handleStateChange,
    onTranscript: handleTranscript,
    onUserMessage: handleUserMessage,
    onAIResponse: handleAIResponse,
    onError: handleError
  });

  try {
    await voiceEngine.start();
    updateAlwaysListeningButton();
    updateUIState(VoiceState.LISTENING);
    await voiceEngine.playGreeting();
    console.log('[NewVoiceMode] Started successfully');
  } catch (error) {
    console.error('[NewVoiceMode] Failed to start:', error);
    await stopNewVoiceMode();
  }
}

async function stopNewVoiceMode() {
  console.log('[NewVoiceMode] Stopping...');
  voiceModeActive = false;

  if (voiceEngine) {
    voiceEngine.stop();
    voiceEngine = null;
  }

  const conversationToggle = document.getElementById('conversationToggle');
  const conversationStatusMessage = document.getElementById('conversationStatusMessage');
  const circleIndicator = document.getElementById('circleIndicator');
  const conversationChatView = document.getElementById('conversationChatView');
  const chatContainer = document.getElementById('chatContainer');
  const inputArea = document.querySelector('.input-area');

  if (chatContainer) {
    chatContainer.style.display = '';
  }

  if (inputArea) {
    inputArea.style.display = '';
  }

  if (conversationToggle) {
    conversationToggle.classList.remove('active');
  }

  if (conversationChatView) {
    conversationChatView.classList.remove('active');
  }

  if (circleIndicator) {
    circleIndicator.classList.remove('active');
    const innerCircle = circleIndicator.querySelector('.circle-indicator');
    if (innerCircle) {
      innerCircle.classList.remove('idle', 'listening', 'speaking');
    }
  }

  if (conversationStatusMessage) {
    conversationStatusMessage.style.display = 'none';
  }

  // Reset always listening to default for next session
  alwaysListening = true;
  updateAlwaysListeningButton();

  console.log('[NewVoiceMode] Stopped');
}

function handleStateChange(state) {
  console.log('[NewVoiceMode] State changed:', state);
  updateUIState(state);
}

function toggleAlwaysListening() {
  alwaysListening = !alwaysListening;
  updateAlwaysListeningButton();

  if (voiceEngine) {
    voiceEngine.setAlwaysListening(alwaysListening);
  }

  // Refresh status message to reflect the new mode
  if (voiceEngine) {
    updateUIState(voiceEngine.getState());
  }
}

function updateAlwaysListeningButton() {
  const alwaysListeningBtn = document.getElementById('alwaysListeningBtn');
  if (!alwaysListeningBtn) return;
  alwaysListeningBtn.classList.toggle('active', alwaysListening);
  const label = alwaysListeningBtn.querySelector('.auto-label');
  if (label) {
    label.textContent = alwaysListening ? 'Auto: ON' : 'Auto: OFF';
  }
}

function updateUIState(state) {
  const conversationStatusMessage = document.getElementById('conversationStatusMessage');
  const circleIndicator = document.getElementById('circleIndicator');
  const conversationMicBtn = document.getElementById('conversationMicBtn');
  const micBtn = document.getElementById('micBtn');

  if (circleIndicator) {
    const innerCircle = circleIndicator.querySelector('.circle-indicator');
    if (innerCircle) {
      innerCircle.classList.remove('idle', 'listening', 'speaking');
      
      switch (state) {
        case VoiceState.LISTENING:
        case VoiceState.IDLE:
          innerCircle.classList.add('idle');
          if (conversationStatusMessage) {
            conversationStatusMessage.textContent = alwaysListening ? '🎤 Ready to listen' : '💬 Type to chat';
            conversationStatusMessage.className = 'conversation-status-message listening';
          }
          break;
        case VoiceState.USER_SPEAKING:
          innerCircle.classList.add('listening');
          if (conversationStatusMessage) {
            conversationStatusMessage.textContent = '🎤 Listening...';
            conversationStatusMessage.className = 'conversation-status-message listening';
          }
          break;
        case VoiceState.THINKING:
          innerCircle.classList.add('speaking');
          if (conversationStatusMessage) {
            conversationStatusMessage.textContent = '🤔 Thinking...';
            conversationStatusMessage.className = 'conversation-status-message speaking';
          }
          break;
        case VoiceState.AI_SPEAKING:
          innerCircle.classList.add('speaking');
          if (conversationStatusMessage) {
            conversationStatusMessage.textContent = '🔊 Speaking...';
            conversationStatusMessage.className = 'conversation-status-message speaking';
          }
          break;
        case VoiceState.INTERRUPTED:
          innerCircle.classList.add('listening');
          if (conversationStatusMessage) {
            conversationStatusMessage.textContent = '🎤 Interrupted - Listening...';
            conversationStatusMessage.className = 'conversation-status-message listening';
          }
          break;
      }
    }
  }

  if (conversationMicBtn) {
    conversationMicBtn.classList.toggle('recording', 
      state === VoiceState.USER_SPEAKING || state === VoiceState.LISTENING);
  }

  if (micBtn) {
    micBtn.classList.toggle('recording', 
      state === VoiceState.USER_SPEAKING || state === VoiceState.LISTENING);
  }
}

function handleTranscript(text) {
  const conversationInput = document.getElementById('conversationInput');
  if (conversationInput) {
    conversationInput.value = text;
    // Keep send button in sync with interim transcript text
    const conversationSendBtn = document.getElementById('conversationSendBtn');
    if (conversationSendBtn) {
      conversationSendBtn.disabled = !text.trim();
    }
  }
}

function submitConversationInput() {
  const conversationInput = document.getElementById('conversationInput');
  if (!conversationInput) return;

  const text = conversationInput.value.trim();
  if (!text) return;

  console.log('[NewVoiceMode] Submitting typed message:', text);

  conversationInput.value = '';
  const conversationSendBtn = document.getElementById('conversationSendBtn');
  if (conversationSendBtn) {
    conversationSendBtn.disabled = true;
  }

  if (voiceEngine) {
    voiceEngine.sendTypedMessage(text);
  } else {
    console.warn('[NewVoiceMode] No voice engine active, cannot send message');
  }
}

function handleUserMessage(text) {
  const conversationMessages = document.getElementById('conversationMessages');
  if (!conversationMessages) return;

  // Clear the input field: for voice-originated messages this removes the
  // interim transcript that was shown there; for typed messages it's a no-op
  // because submitConversationInput() already cleared it.
  const conversationInput = document.getElementById('conversationInput');
  if (conversationInput) {
    conversationInput.value = '';
  }
  const conversationSendBtn = document.getElementById('conversationSendBtn');
  if (conversationSendBtn) {
    conversationSendBtn.disabled = true;
  }

  const msgDiv = document.createElement('div');
  msgDiv.className = 'conversation-message user';

  const avatarDiv = document.createElement('div');
  avatarDiv.className = 'conversation-message-avatar';
  avatarDiv.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M20 21V19C20 17.9391 19.5786 16.9217 18.8284 16.1716C18.0783 15.4214 17.0609 15 16 15H8C6.93913 15 5.92172 15.4214 5.17157 16.1716C4.42143 16.9217 4 17.9391 4 19V21" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><circle cx="12" cy="7" r="4" stroke="currentColor" stroke-width="2"/></svg>`;

  const contentDiv = document.createElement('div');
  contentDiv.className = 'conversation-message-content';
  contentDiv.textContent = text;

  msgDiv.appendChild(avatarDiv);
  msgDiv.appendChild(contentDiv);
  conversationMessages.appendChild(msgDiv);
  conversationMessages.scrollTop = conversationMessages.scrollHeight;

  // Auto-show messages panel so user sees their message
  conversationMessages.classList.remove('hidden');
  const toggleMessagesBtn = document.getElementById('toggleMessagesBtn');
  if (toggleMessagesBtn) {
    const label = toggleMessagesBtn.querySelector('span');
    if (label) label.textContent = 'Messages';
  }
}

function handleAIResponse(text) {
  const conversationMessages = document.getElementById('conversationMessages');
  if (!conversationMessages) return;

  let lastMessage = conversationMessages.lastElementChild;
  
  if (!lastMessage || !lastMessage.classList.contains('ai')) {
    lastMessage = document.createElement('div');
    lastMessage.className = 'conversation-message ai';
    
    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'conversation-message-avatar';
    avatarDiv.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M12 2C8.13 2 5 5.13 5 9C5 11.38 6.19 13.47 8 14.74V17" stroke="currentColor" stroke-width="2"/><path d="M12 14.74C13.81 13.47 15 11.38 15 9C15 5.13 11.87 2 8 2" stroke="currentColor" stroke-width="2"/><path d="M12 17V21M8 23H16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'conversation-message-content';
    contentDiv.textContent = text;
    
    lastMessage.appendChild(avatarDiv);
    lastMessage.appendChild(contentDiv);
    conversationMessages.appendChild(lastMessage);
  } else {
    const contentDiv = lastMessage.querySelector('.conversation-message-content');
    if (contentDiv) {
      contentDiv.textContent = text;
    }
  }

  conversationMessages.scrollTop = conversationMessages.scrollHeight;
}

function handleError(error) {
  console.error('[NewVoiceMode] Error:', error);
  
  const conversationStatusMessage = document.getElementById('conversationStatusMessage');
  if (conversationStatusMessage) {
    conversationStatusMessage.textContent = '❌ Error: ' + error.message;
    conversationStatusMessage.className = 'conversation-status-message error';
  }
}

export function isVoiceModeActive() {
  return voiceModeActive;
}

export function getVoiceEngine() {
  return voiceEngine;
}

export default {
  init: initNewVoiceMode,
  start: startNewVoiceMode,
  stop: stopNewVoiceMode,
  isActive: isVoiceModeActive,
  getEngine: getVoiceEngine
};

if (typeof window !== 'undefined') {
  window.NewVoiceMode = {
    init: initNewVoiceMode,
    start: startNewVoiceMode,
    stop: stopNewVoiceMode,
    isActive: isVoiceModeActive,
    getEngine: getVoiceEngine
  };
  
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      setTimeout(initNewVoiceMode, 100);
    });
  } else {
    setTimeout(initNewVoiceMode, 100);
  }
}