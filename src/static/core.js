/**
 * LM Studio Chatbot - Core Module
 * DOM Elements, State, and Initialization
 */

console.log('[CORE] core.js loading...');

// ============================================================
// GLOBAL TTS PLAYBACK MODE - ONLY ONE CAN BE ACTIVE
// ============================================================
window.TTS_PLAYBACK_MODE = "stream"; 
console.log('[CORE] TTS_PLAYBACK_MODE initialized to:', window.TTS_PLAYBACK_MODE);
// Allowed values: "stream", "websocket"
// "stream" = Use AudioContext for streaming PCM chunks (AudioWorklet)
// "websocket" = Use WebSocket + AudioContext streaming

// Initialize audio context for WAV mode to ensure audio works
let wavAudioContext = null;

function initWavAudioContext() {
    if (window.TTS_PLAYBACK_MODE === "stream" || window.TTS_PLAYBACK_MODE === "websocket") {
        console.log("[AUDIO] Skipping initWavAudioContext - streaming mode active");
        return;
    }
    try {
        if (!wavAudioContext) {
            wavAudioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 48000,
                latencyHint: 'interactive'
            });
            console.log("[AUDIO] Initialized WAV AudioContext:", wavAudioContext.sampleRate + "Hz");
        }
        
        // Resume if suspended (required by browsers after user interaction)
        if (wavAudioContext.state === 'suspended') {
            wavAudioContext.resume();
        }
    } catch (error) {
        console.warn("[AUDIO] Failed to initialize WAV AudioContext:", error);
    }
}


// ============================================================
// HARD AUDIOCONTEXT CLEANUP - Call when switching to WAV mode
// ============================================================
function destroyAllAudioContexts() {
    // Close streaming AudioContext from websocket.js
    if (window.streamingAudioContext) {
        try {
            window.streamingAudioContext.close();
            console.log("[AUDIO] Closed streamingAudioContext");
        } catch (e) {}
        window.streamingAudioContext = null;
    }
    
    // Close any other AudioContext references
    if (window.wsAudioCtx) {
        try {
            window.wsAudioCtx.close();
            console.log("[AUDIO] Closed wsAudioCtx");
        } catch (e) {}
        window.wsAudioCtx = null;
    }
    
    // Reset state variables
    if (typeof previousChunkEnd !== 'undefined') {
        previousChunkEnd = null;
    }
    if (typeof nextChunkStartTime !== 'undefined') {
        nextChunkStartTime = 0;
    }
}

// ============================================================
// DOM Elements
// ============================================================
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const messagesContainer = document.getElementById('messages');
const chatContainer = document.getElementById('chatContainer');
const welcomeMessage = document.getElementById('welcomeMessage');
const typingIndicator = document.getElementById('typingIndicator');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const modelSelect = document.getElementById('modelSelect');
const clearBtn = document.getElementById('clearBtn');
const sidebar = document.getElementById('sidebar');
const sessionList = document.getElementById('sessionList');
const newChatBtn = document.getElementById('newChatBtn');
const toggleSidebarBtn = document.getElementById('toggleSidebar');
const settingsBtn = document.getElementById('settingsBtn');
const settingsModal = document.getElementById('settingsModal');
const closeSettings = document.getElementById('closeSettings');
const systemPromptInput = document.getElementById('systemPrompt');
const globalSystemPromptInput = document.getElementById('globalSystemPrompt');
const saveSettings = document.getElementById('saveSettings');
const providerSelect = document.getElementById('providerSelect');
const lmstudioSettings = document.getElementById('lmstudioSettings');
const openrouterSettings = document.getElementById('openrouterSettings');
const lmstudioUrlInput = document.getElementById('lmstudioUrl');
const lmstudioDirectInput = document.getElementById('lmstudioDirect');
const openrouterApiKeyInput = document.getElementById('openrouterApiKey');
const openrouterModelInput = document.getElementById('openrouterModel');
const openrouterContextInput = document.getElementById('openrouterContext');
const openrouterThinkingInput = document.getElementById('openrouterThinking');
const loadOpenRouterModelsBtn = document.getElementById('loadOpenRouterModels');
const ttsSpeaker = document.getElementById('ttsSpeaker');
const cerebrasApiKeyInput = document.getElementById('cerebrasApiKey');
const cerebrasModelInput = document.getElementById('cerebrasModel');
const cerebrasSettings = document.getElementById('cerebrasSettings');
const loadCerebrasModelsBtn = document.getElementById('loadCerebrasModels');
const openaiCompatibleSettings = document.getElementById('openaiCompatibleSettings');
const openaiCompatibleUrl = document.getElementById('openaiCompatibleUrl');
const openaiCompatibleApiKey = document.getElementById('openaiCompatibleApiKey');
const openaiCompatibleModel = document.getElementById('openaiCompatibleModel');
const openaiCompatibleThinking = document.getElementById('openaiCompatibleThinking');
const openaiCompatibleTimeout = document.getElementById('openaiCompatibleTimeout');
const loadOpenAiCompatibleModelsBtn = document.getElementById('loadOpenAiCompatibleModels');
const customHeadersContainer = document.getElementById('customHeadersContainer');
const addCustomHeaderBtn = document.getElementById('addCustomHeaderBtn');
const llamacppSettings = document.getElementById('llamacppSettings');
const llamacppUrlInput = document.getElementById('llamacppUrl');
const llamacppModelInput = document.getElementById('llamacppModel');
const huggingfaceTokenInput = document.getElementById('huggingfaceToken');
const hfTokenInput = document.getElementById('hfToken');
const llamacppAutoStart = document.getElementById('llamacppAutoStart');
const llamacppDownloadLocation = document.getElementById('llamacppDownloadLocation');

// State
var sessionId = null;
let isLoading = false;
let sessions = [];

// WebSocket Configuration - removed realtime server references
// USE_WEBSOCKET is now controlled by TTS_PLAYBACK_MODE
// In "stream" mode: USE_WEBSOCKET = true (use AudioContext + AudioWorklet)
// In "websocket" mode: USE_WEBSOCKET = true (use WebSocket + AudioContext streaming)
const ENABLE_STREAMING_TTS = true; // Set to true for streaming TTS

// Dynamic getter for USE_WEBSOCKET based on playback mode
function getUseWebSocket() {
    if (window.TTS_PLAYBACK_MODE === "stream") {
        return true;
    } else if (window.TTS_PLAYBACK_MODE === "websocket") {
        return true;
    } else {
        console.warn("Unexpected TTS_PLAYBACK_MODE:", window.TTS_PLAYBACK_MODE);
        return false;
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    console.log('Page loaded, starting initialization...');
    
    // Only initialize WAV audio context for non-streaming modes
    if (window.TTS_PLAYBACK_MODE !== "stream" && window.TTS_PLAYBACK_MODE !== "websocket") {
        initWavAudioContext();
    } else {
        console.log('[CORE] Skipping WAV AudioContext init (streaming mode active)');
    }
    
    // Load UI elements FIRST (no await - these are fast and make UI appear immediately)
    console.log('=== SETUP STEP 1: Event listeners ===');
    setupEventListeners();
    console.log('=== SETUP STEP 2: File attachments ===');
    if (typeof setupFileAttachments === 'function') {
        console.log('=== CALLING setupFileAttachments NOW ===');
        setupFileAttachments();
        console.log('=== setupFileAttachments returned ===');
    } else {
        console.error('!!! setupFileAttachments is NOT a function !!!');
    }
    console.log('=== SETUP STEP 3: Loading sessions ===');
    // Use SessionManager.loadSessions if available, otherwise create a fallback
    if (typeof SessionManager?.loadSessions === 'function') {
        SessionManager.loadSessions();
    } else {
        console.warn('[CORE] SessionManager.loadSessions not available, using fallback');
        // Fallback: create a new session manually
        if (typeof createNewSession === 'function') {
            createNewSession();
        }
    }
    console.log('Loading TTS speakers...');
    loadTTSSpeakers();
    
    // Then load settings and check health in the background (don't block UI)
    console.log('Loading settings (in background)...');
    loadSettings().then(async () => {
        // Auto-start llama.cpp server FIRST before checking health
        console.log('Auto-starting llama.cpp server if configured...');
        await autoStartLlamaCppServer();
        
        console.log('Settings loaded, checking health...');
        checkHealth();
    }).catch(err => {
        console.error('Error loading settings:', err);
    });
    
    console.log('UI initialized, health check running in background...');
    setInterval(checkHealth, 30000);
});

// Setup event listeners
function setupEventListeners() {
    console.log('[CORE] Setting up event listeners...');
    
    // Use wrapper function to ensure sendMessage exists
    sendBtn.addEventListener('click', () => {
        console.log('[CORE] Send button clicked');
        if (typeof sendMessage === 'function') {
            sendMessage();
        } else {
            console.error('[CORE] sendMessage is not defined!');
        }
    });
    
    messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            console.log('[CORE] Enter pressed, message:', messageInput.value.trim());
            if (typeof sendMessage === 'function') {
                sendMessage();
            } else {
                console.error('[CORE] sendMessage is not defined!');
            }
        }
    });
    
    messageInput.addEventListener('input', () => {
        messageInput.style.height = 'auto';
        messageInput.style.height = Math.min(messageInput.scrollHeight, 150) + 'px';
        sendBtn.disabled = !messageInput.value.trim() || isLoading;
    });
    
    clearBtn.addEventListener('click', () => {
        if (typeof ChatAPI?.clearChat === 'function') {
            ChatAPI.clearChat();
        } else {
            console.warn('[CORE] ChatAPI.clearChat not available, using fallback');
            // Fallback: clear messages and call API directly
            messagesContainer.innerHTML = '';
            welcomeMessage.classList.remove('hidden');
            if (sessionId) {
                fetch('/api/clear', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ session_id: sessionId })
                }).catch(err => console.error('Error clearing session:', err));
            }
            messageInput.focus();
        }
    });
    modelSelect.addEventListener('change', () => {
        sessionStorage.setItem('selectedModel', modelSelect.value);
    });
    
    // Sidebar logo button (in sidebar header) - shows collapse icon on hover
    const sidebarLogoBtn = document.getElementById('sidebarLogoBtn');
    if (sidebarLogoBtn) {
        sidebarLogoBtn.addEventListener('click', () => {
            // Toggle between collapsed and expanded
            if (sidebar.classList.contains('collapsed')) {
                sidebar.classList.remove('collapsed');
            } else {
                sidebar.classList.add('collapsed');
            }
            updateSidebarButtons();
        });
    }
    
    // Sidebar collapse button (inside sidebar header) - collapses sidebar
    const sidebarCollapseBtn = document.getElementById('sidebarCollapseBtn');
    if (sidebarCollapseBtn) {
        sidebarCollapseBtn.addEventListener('click', () => {
            sidebar.classList.add('collapsed');
            updateSidebarButtons();
        });
    }
    
    // Expand sidebar button (floating) - expands sidebar when collapsed
    const expandSidebarBtn = document.getElementById('expandSidebarBtn');
    if (expandSidebarBtn) {
        expandSidebarBtn.addEventListener('click', () => {
            sidebar.classList.remove('collapsed');
            updateSidebarButtons();
        });
    }
    
    // Sidebar toggle button (in header) - expands sidebar when collapsed
    // Note: toggleSidebarBtn may be null if the button was removed from HTML
    if (toggleSidebarBtn) {
        toggleSidebarBtn.addEventListener('click', () => {
            sidebar.classList.remove('collapsed');
            updateSidebarButtons();
        });
    }
    
    // Update buttons visibility based on sidebar state
    function updateSidebarButtons() {
        const isCollapsed = sidebar.classList.contains('collapsed');
        
        // Show header toggle button only when collapsed (to expand)
        // Note: toggleSidebarBtn may be null if the button was removed from HTML
        if (toggleSidebarBtn) {
            toggleSidebarBtn.style.display = isCollapsed ? 'flex' : 'none';
        }
        
        // Show floating expand button when collapsed
        const expandSidebarBtn = document.getElementById('expandSidebarBtn');
        if (expandSidebarBtn) {
            expandSidebarBtn.style.display = isCollapsed ? 'flex' : 'none';
        }
        
        // Show sidebar logo button only when expanded (to collapse)
        if (sidebarLogoBtn) {
            sidebarLogoBtn.style.display = isCollapsed ? 'none' : 'flex';
        }
        
        // Show collapsed icons container only when collapsed
        const sidebarCollapsedIcons = document.getElementById('sidebarCollapsedIcons');
        if (sidebarCollapsedIcons) {
            sidebarCollapsedIcons.style.display = isCollapsed ? 'flex' : 'none';
        }
    }
    
    // Initialize - sidebar starts collapsed by CSS
    updateSidebarButtons();
    
    // New chat button in sidebar options
    const newChatBtnOption = document.getElementById('newChatBtnOption');
    if (newChatBtnOption) {
        newChatBtnOption.addEventListener('click', () => {
            createNewSession();
        });
    }
    
    // Settings button in sidebar options
    const settingsBtnOption = document.getElementById('settingsBtnOption');
    if (settingsBtnOption) {
        settingsBtnOption.addEventListener('click', () => {
            loadSettings();
            settingsModal.classList.add('active');
        });
    }
    
    // Search chat button in sidebar options
    const searchChatBtnOption = document.getElementById('searchChatBtnOption');
    const searchChatModal = document.getElementById('searchChatModal');
    const closeSearchChat = document.getElementById('closeSearchChat');
    const searchChatInput = document.getElementById('searchChatInput');
    const searchChatResults = document.getElementById('searchChatResults');
    
    if (searchChatBtnOption && searchChatModal) {
        searchChatBtnOption.addEventListener('click', () => {
            searchChatModal.classList.add('active');
            if (searchChatInput) {
                searchChatInput.value = '';
                searchChatInput.focus();
            }
            if (searchChatResults) {
                searchChatResults.innerHTML = '';
            }
        });
        
        if (closeSearchChat) {
            closeSearchChat.addEventListener('click', () => {
                searchChatModal.classList.remove('active');
            });
        }
        
        searchChatModal.addEventListener('click', (e) => {
            if (e.target === searchChatModal) {
                searchChatModal.classList.remove('active');
            }
        });
        
        // Search chat functionality
        if (searchChatInput) {
            searchChatInput.addEventListener('input', debounce(async () => {
                const query = searchChatInput.value.trim().toLowerCase();
                if (query.length < 2) {
                    if (searchChatResults) {
                        searchChatResults.innerHTML = '';
                    }
                    return;
                }
                
                await performChatSearch(query);
            }, 300));
        }
    }
    
    // Perform chat search
    async function performChatSearch(query) {
        if (!searchChatResults) return;
        
        try {
            const response = await fetch('/api/sessions');
            const data = await response.json();
            
            if (!data.success || !data.sessions) {
                searchChatResults.innerHTML = '<p class="search-chat-no-results">No sessions found</p>';
                return;
            }
            
            const results = [];
            
            // Fetch each session individually to get messages
            // The /api/sessions endpoint only returns metadata, not messages
            for (const session of data.sessions) {
                try {
                    const sessionResponse = await fetch(`/api/sessions/${session.id}`);
                    const sessionData = await sessionResponse.json();
                    
                    console.log('[SEARCH] Fetched session:', session.id, sessionData.success ? 'OK' : 'FAIL');
                    
                    if (sessionData.success && sessionData.session) {
                        const fullSession = sessionData.session;
                        // Add the session ID to the session object (API doesn't include it)
                        fullSession.id = session.id;
                        
                        console.log('[SEARCH] Session has messages:', fullSession.messages ? fullSession.messages.length : 0);
                        
                        // Check messages - search both user and AI messages
                        if (fullSession.messages) {
                            for (const msg of fullSession.messages) {
                                if (msg.content && msg.content.toLowerCase().includes(query)) {
                                    results.push({
                                        session: fullSession,
                                        type: 'message',
                                        match: msg.content,
                                        role: msg.role
                                    });
                                }
                            }
                        }
                    }
                } catch (e) {
                    console.error('Error fetching session:', session.id, e);
                }
            }
            
            if (results.length === 0) {
                searchChatResults.innerHTML = '<p class="search-chat-no-results">No results found for "' + query + '"</p>';
                return;
            }
            
            // Display results
            console.log('[SEARCH] Building results for query:', query);
            searchChatResults.innerHTML = results.slice(0, 20).map(result => {
                const sessionTitle = result.session.title || 'Untitled Chat';
                const sessionId = result.session.id;
                let contentPreview = result.match;
                
                console.log('[SEARCH] Result session ID:', sessionId);
                
                // Truncate and highlight
                if (contentPreview.length > 150) {
                    const idx = contentPreview.toLowerCase().indexOf(query);
                    const start = Math.max(0, idx - 50);
                    const end = Math.min(contentPreview.length, idx + query.length + 100);
                    contentPreview = (start > 0 ? '...' : '') + 
                        contentPreview.substring(start, end).replace(
                            new RegExp('(' + query + ')', 'gi'), 
                            '<mark>$1</mark>'
                        ) + 
                        (end < contentPreview.length ? '...' : '');
                } else {
                    contentPreview = contentPreview.replace(
                        new RegExp('(' + query + ')', 'gi'), 
                        '<mark>$1</mark>'
                    );
                }
                
                return `
                    <div class="search-chat-result-item" data-session-id="${sessionId}">
                        <div class="search-chat-result-session">${sessionTitle} ${result.type === 'message' ? '- ' + (result.role || 'message') : ''}</div>
                        <div class="search-chat-result-content">${contentPreview}</div>
                    </div>
                `;
            }).join('');
            
            console.log('[SEARCH] HTML generated, checking data attributes');
            document.querySelectorAll('.search-chat-result-item').forEach((item, idx) => {
                console.log('[SEARCH] Item', idx, 'data-session-id:', item.getAttribute('data-session-id'), 'dataset.sessionId:', item.dataset.sessionId);
            });
            
            // Add click handlers to results
            document.querySelectorAll('.search-chat-result-item').forEach(item => {
                item.addEventListener('click', async () => {
                    const targetSessionId = item.dataset.sessionId;
                    const searchText = query; // Store the search query for scrolling
                    
                    // Close search modal FIRST
                    searchChatModal.classList.remove('active');
                    
                    // Expand sidebar if collapsed (need to do this before switching)
                    sidebar.classList.remove('collapsed');
                    updateSidebarButtons();
                    
                    // Load the session FIRST and wait for it to complete
                    console.log('[SEARCH] Loading session:', targetSessionId);
                    
                    // Use loadSession directly to ensure it completes before scrolling
                    try {
                        console.log('[SEARCH] Fetching session from:', `/api/sessions/${targetSessionId}`);
                        const response = await fetch(`/api/sessions/${targetSessionId}`);
                        const data = await response.json();
                        
                        console.log('[SEARCH] Session response:', data);
                        
                        if (data.success && data.session) {
                            // Update global sessionId
                            sessionId = targetSessionId;
                            
                            // Render the messages
                            messagesContainer.innerHTML = '';
                            const messages = data.session.messages || [];
                            
                            if (messages.length === 0) {
                                welcomeMessage.classList.remove('hidden');
                            } else {
                                welcomeMessage.classList.add('hidden');
                                
                                messages.forEach(msg => {
                                    if (msg.role !== 'system') {
                                        addMessage(msg.role, msg.content, msg.thinking || null);
                                    }
                                });
                            }
                            
                            // Update system prompt if present
                            if (data.session.system_prompt) {
                                systemPromptInput.value = data.session.system_prompt;
                            }
                            
                            // Don't call loadSessions() here as it might reset the view
                            // The session list will be updated when user next interacts with sidebar
                            
                            console.log('[SEARCH] Session loaded, messages count:', messages.length);
                            
                            // NOW scroll to the message after session is fully loaded
                            setTimeout(() => {
                                const messageElements = messagesContainer.querySelectorAll('.message');
                                console.log('[SEARCH] Found', messageElements.length, 'message elements');
                                
                                let found = false;
                                for (let i = 0; i < messageElements.length; i++) {
                                    const msg = messageElements[i];
                                    const content = msg.querySelector('.message-content');
                                    const messageText = content ? content.textContent : msg.textContent;
                                    
                                    if (messageText && messageText.toLowerCase().includes(searchText.toLowerCase())) {
                                        console.log('[SEARCH] Found match in message', i);
                                        msg.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                        msg.style.backgroundColor = 'rgba(255, 255, 0, 0.3)';
                                        setTimeout(() => {
                                            msg.style.backgroundColor = '';
                                        }, 3000);
                                        found = true;
                                        break;
                                    }
                                }
                                
                                if (!found) {
                                    console.log('[SEARCH] No match, scrolling to bottom');
                                    chatContainer.scrollTop = chatContainer.scrollHeight;
                                }
                            }, 100);
                        } else {
                            console.error('[SEARCH] Failed to load session');
                        }
                    } catch (error) {
                        console.error('[SEARCH] Error loading session:', error);
                    }
                });
            });
            
        } catch (error) {
            console.error('Search error:', error);
            searchChatResults.innerHTML = '<p class="search-chat-no-results">Error performing search</p>';
        }
    }
    
    // Debounce utility
    function debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
    
    // Keep original newChatBtn for compatibility
    const newChatBtn = document.getElementById('newChatBtn');
    if (newChatBtn) {
        newChatBtn.addEventListener('click', createNewSession);
    }
    
    // New collapsed sidebar buttons
    const newChatBtnCollapsed = document.getElementById('newChatBtnCollapsed');
    if (newChatBtnCollapsed) {
        newChatBtnCollapsed.addEventListener('click', () => {
            createNewSession();
        });
    }
    
    const searchChatBtnCollapsed = document.getElementById('searchChatBtnCollapsed');
    if (searchChatBtnCollapsed && searchChatModal) {
        searchChatBtnCollapsed.addEventListener('click', () => {
            searchChatModal.classList.add('active');
            if (searchChatInput) {
                searchChatInput.value = '';
                searchChatInput.focus();
            }
            if (searchChatResults) {
                searchChatResults.innerHTML = '';
            }
        });
    }
    
    // Voice Clone button in collapsed sidebar
    const voiceCloneBtnCollapsed = document.getElementById('voiceCloneBtnCollapsed');
    if (voiceCloneBtnCollapsed) {
        voiceCloneBtnCollapsed.addEventListener('click', () => {
            // Open voice clone modal - use the header button handler
            const voiceCloneModal = document.getElementById('voiceCloneModal');
            if (voiceCloneModal) {
                voiceCloneModal.classList.add('active');
            }
        });
    }
    
    // Audiobook button in collapsed sidebar
    const audiobookBtnCollapsed = document.getElementById('audiobookBtnCollapsed');
    if (audiobookBtnCollapsed) {
        audiobookBtnCollapsed.addEventListener('click', () => {
            if (typeof openAudiobookModal === 'function') {
                openAudiobookModal();
            }
        });
    }
    
    // Podcast button in collapsed sidebar
    const podcastBtnCollapsed = document.getElementById('podcastBtnCollapsed');
    if (podcastBtnCollapsed) {
        podcastBtnCollapsed.addEventListener('click', () => {
            // Open podcast modal
            const podcastModal = document.getElementById('podcast-modal');
            if (podcastModal) {
                podcastModal.classList.add('active');
            }
        });
    }
    
    // Settings button in collapsed sidebar
    const settingsBtnCollapsed = document.getElementById('settingsBtnCollapsed');
    if (settingsBtnCollapsed) {
        settingsBtnCollapsed.addEventListener('click', () => {
            // Open modal immediately for responsiveness, load settings in background
            settingsModal.classList.add('active');
            loadSettings();
            // Load LLM models for llama.cpp if provider is already llama.cpp
            if (providerSelect && providerSelect.value === 'llamacpp') {
                loadLlmModelsForLlamaCpp();
            }
        });
    }
    
    // Settings button in header
    if (settingsBtn) {
        settingsBtn.addEventListener('click', () => {
            // Open modal immediately for responsiveness, load settings in background
            settingsModal.classList.add('active');
            loadSettings();
            // Load LLM models for llama.cpp if provider is already llama.cpp
            if (providerSelect && providerSelect.value === 'llamacpp') {
                loadLlmModelsForLlamaCpp();
            }
        });
    }
    
    closeSettings.addEventListener('click', () => {
        settingsModal.classList.remove('active');
    });
    
    settingsModal.addEventListener('click', (e) => {
        if (e.target === settingsModal) {
            settingsModal.classList.remove('active');
        }
    });
    
    saveSettings.addEventListener('click', saveSettingsHandler);
    
    providerSelect.addEventListener('change', async () => {
        const provider = providerSelect.value;
        lmstudioSettings.style.display = provider === 'lmstudio' ? 'block' : 'none';
        openrouterSettings.style.display = provider === 'openrouter' ? 'block' : 'none';
        cerebrasSettings.style.display = provider === 'cerebras' ? 'block' : 'none';
        llamacppSettings.style.display = provider === 'llamacpp' ? 'block' : 'none';
        openaiCompatibleSettings.style.display = provider === 'openai_compatible' ? 'block' : 'none';
        
        // Load saved API keys and settings when switching providers
        if (provider === 'cerebras') {
            // Load Cerebras settings to show saved API key
            await loadCerebrasSettings();
        } else if (provider === 'openrouter') {
            // Load OpenRouter settings to show saved API key
            await loadOpenRouterSettings();
        }
        
        // Load LLM models for llama.cpp when provider is switched to llama.cpp
        if (provider === 'llamacpp') {
            loadLlmModelsForLlamaCpp();
        }
    });
    
    loadOpenRouterModelsBtn.addEventListener('click', loadOpenRouterModels);
    
    if (loadCerebrasModelsBtn) {
        loadCerebrasModelsBtn.addEventListener('click', loadCerebrasModels);
    }
    
    // OpenAI Compatible models button
    if (loadOpenAiCompatibleModelsBtn) {
        loadOpenAiCompatibleModelsBtn.addEventListener('click', loadOpenAiCompatibleModels);
    }
    
    // Custom headers functionality
    if (addCustomHeaderBtn) {
        addCustomHeaderBtn.addEventListener('click', addCustomHeader);
    }
    
    // Save speaker selection when changed and trigger immediate voice test
    if (ttsSpeaker) {
        ttsSpeaker.addEventListener('change', async () => {
            localStorage.setItem('selectedSpeaker', ttsSpeaker.value);
            console.log('[CORE] Saved speaker selection:', ttsSpeaker.value);
        });
    }
    
    // Preserve llama.cpp model selection when dropdown is interacted with
    if (llamacppModelInput) {
        llamacppModelInput.addEventListener('focus', () => {
            // Save current selection when dropdown gets focus
            localStorage.setItem('llamacpp_selected_model', llamacppModelInput.value);
        });
        llamacppModelInput.addEventListener('change', () => {
            const selected = llamacppModelInput.value;
            console.log('[CORE] Llama.cpp model selected:', selected);
            localStorage.setItem('llamacpp_selected_model', selected);
        });
    }
}

// File attachment handling
function setupFileAttachments() {
    console.log('!!! INSIDE setupFileAttachments function !!!');
    console.log('[CORE] Setting up file attachments...');
    
    const fileInput = document.getElementById('fileInput');
    const fileBtn = document.getElementById('fileBtn');
    const attachmentPreview = document.getElementById('attachmentPreview');
    
    console.log('[CORE] fileBtn:', fileBtn);
    console.log('[CORE] fileInput:', fileInput);
    console.log('[CORE] attachmentPreview:', attachmentPreview);
    
    if (fileBtn) {
        console.log('[CORE] fileBtn offsetWidth:', fileBtn.offsetWidth);
        console.log('[CORE] fileBtn offsetHeight:', fileBtn.offsetHeight);
        console.log('[CORE] fileBtn style.display:', fileBtn.style.display);
        console.log('[CORE] fileBtn getComputedStyle display:', window.getComputedStyle(fileBtn).display);
        console.log('[CORE] fileBtn className:', fileBtn.className);
        console.log('[CORE] fileBtn z-index:', window.getComputedStyle(fileBtn).zIndex);
        console.log('[CORE] fileBtn pointer-events:', window.getComputedStyle(fileBtn).pointerEvents);
        
        // Check if it's covered by something
        const rect = fileBtn.getBoundingClientRect();
        console.log('[CORE] fileBtn rect:', rect);
    }
    
    let attachments = [];
    const MAX_FILES = 5;
    const MAX_SIZE = 30 * 1024 * 1024;

    if (fileBtn && fileInput) {
        console.log('[CORE] Adding event listeners to fileBtn and fileInput');
        
        // Global click debug
        document.addEventListener('click', (e) => {
            if (e.target === fileBtn || fileBtn.contains(e.target)) {
                console.log('[CORE] Global click on fileBtn detected!');
            }
        });
        
        // Direct onclick as fallback
        fileBtn.onclick = function(e) {
            console.log('[CORE] fileBtn onclick fired');
            e.preventDefault();
            e.stopPropagation();
            // Use setTimeout to ensure the click is in a new event loop
            setTimeout(() => {
                console.log('[CORE] Triggering file input click');
                fileInput.click();
            }, 0);
        };
        
        fileBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            console.log('[CORE] File button CLICKED via addEventListener');
            setTimeout(() => {
                fileInput.click();
            }, 0);
        });

        fileInput.addEventListener('change', (e) => {
            console.log('[CORE] File input CHANGE event:', e);
            handleFileSelect(e);
        });
        
        // Also try mousedown
        fileBtn.addEventListener('mousedown', (e) => {
            console.log('[CORE] File button MOUSEDOWN');
        });
        
        // Expose for testing
        window.testFileBtn = function() {
            console.log('[CORE] Testing fileBtn click');
            fileInput.click();
        };
    } else {
        console.error('[CORE] fileBtn or fileInput not found!');
    }

    function handleFileSelect(e) {
        const files = Array.from(e.target.files);
        if (files.length === 0) return;

        const currentSize = attachments.reduce((sum, f) => sum + f.size, 0);
        const newSize = files.reduce((sum, f) => sum + f.size, 0);

        if (attachments.length + files.length > MAX_FILES) {
            alert(`Maximum ${MAX_FILES} files allowed`);
            return;
        }

        if (currentSize + newSize > MAX_SIZE) {
            alert('Maximum total size is 30MB');
            return;
        }

        for (const file of files) {
            if (!file.type.match(/^image\/(png|jpeg|jpg|gif|webp|bmp|svg)$/) && 
                !file.name.match(/\.(pdf|docx|txt|csv|png|jpe?g|gif|webp|bmp|svg)$/i)) {
                alert('Unsupported file type. Supported: images, PDF, DOCX, TXT, CSV');
                continue;
            }
            attachments.push(file);
        }

        renderAttachments();
        fileInput.value = '';
        updateSendButton();
    }

    function renderAttachments() {
        attachmentPreview.innerHTML = '';
        
        attachments.forEach((file, index) => {
            const item = document.createElement('div');
            item.className = 'attachment-item';
            
            if (file.type.startsWith('image/')) {
                item.classList.add('image-preview');
                const img = document.createElement('img');
                img.src = URL.createObjectURL(file);
                item.appendChild(img);
            } else {
                const icon = document.createElement('div');
                icon.className = 'attachment-icon';
                icon.innerHTML = getFileIcon(file.name);
                item.appendChild(icon);
            }
            
            const name = document.createElement('span');
            name.className = 'attachment-name';
            name.textContent = file.name;
            item.appendChild(name);
            
            const size = document.createElement('span');
            size.className = 'attachment-size';
            size.textContent = formatFileSize(file.size);
            item.appendChild(size);
            
            const removeBtn = document.createElement('button');
            removeBtn.className = 'remove-attachment';
            removeBtn.innerHTML = '&times;';
            removeBtn.onclick = () => removeAttachment(index);
            item.appendChild(removeBtn);
            
            attachmentPreview.appendChild(item);
        });
    }

    function getFileIcon(filename) {
        const ext = filename.split('.').pop().toLowerCase();
        const icons = {
            pdf: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>',
            docx: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/></svg>',
            txt: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/></svg>',
            csv: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="12" x2="16" y2="12"/><line x1="8" y1="16" x2="16" y2="16"/><line x1="8" y1="20" x2="16" y2="20"/></svg>'
        };
        return icons[ext] || icons.txt;
    }

    function formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    function removeAttachment(index) {
        attachments.splice(index, 1);
        renderAttachments();
        updateSendButton();
    }

    function updateSendButton() {
        if (sendBtn) {
            sendBtn.disabled = (!messageInput.value.trim() || isLoading) && attachments.length === 0;
        }
    }

    window.getAttachments = () => {
        console.log('[DEBUG] getAttachments called, returning:', attachments);
        return attachments;
    };
    window.clearAttachments = () => {
        attachments = [];
        renderAttachments();
    };
}

// Add custom header field
function addCustomHeader() {
    if (!customHeadersContainer) return;
    
    const headerDiv = document.createElement('div');
    headerDiv.className = 'custom-header-field';
    headerDiv.innerHTML = `
        <input type="text" placeholder="Header name" class="custom-header-name" />
        <input type="text" placeholder="Header value" class="custom-header-value" />
        <button type="button" class="remove-header-btn" onclick="removeCustomHeader(this)">Remove</button>
    `;
    
    customHeadersContainer.appendChild(headerDiv);
}

// Remove custom header field
function removeCustomHeader(button) {
    if (!customHeadersContainer) return;
    
    const headerDiv = button.closest('.custom-header-field');
    if (headerDiv) {
        customHeadersContainer.removeChild(headerDiv);
    }
}

// Load settings
async function loadSettings() {
    try {
        const response = await fetch('/api/settings');
        const data = await response.json();
        
        console.log('Settings loaded:', data);
        
        if (data.success) {
            const settings = data.settings;
            providerSelect.value = settings.provider || 'cerebras';
            
            if (settings.lmstudio) {
                lmstudioUrlInput.value = settings.lmstudio.base_url || 'http://localhost:1234';
                if (lmstudioDirectInput) {
                    lmstudioDirectInput.checked = settings.lmstudio.direct || false;
                }
            }
            
            if (settings.openrouter) {
                const storedApiKey = settings.openrouter.api_key;
                if (storedApiKey && storedApiKey.length > 4) {
                    openrouterApiKeyInput.placeholder = '••••' + storedApiKey.slice(-4);
                } else if (storedApiKey) {
                    openrouterApiKeyInput.placeholder = 'API key saved';
                } else {
                    openrouterApiKeyInput.placeholder = 'sk-or-...';
                }
                openrouterModelInput.value = settings.openrouter.model || 'openai/gpt-4o-mini';
                openrouterContextInput.value = settings.openrouter.context_size || 128000;
                openrouterThinkingInput.value = settings.openrouter.thinking_budget || 0;
            }
            
            if (settings.cerebras) {
                if (cerebrasApiKeyInput) {
                    const storedApiKey = settings.cerebras.api_key;
                    if (storedApiKey && storedApiKey.length > 4) {
                        // Show masked key in the input field (first 8 chars + ...)
                        const maskedKey = storedApiKey.substring(0, 8) + '...' + storedApiKey.slice(-4);
                        cerebrasApiKeyInput.value = maskedKey;
                    } else if (storedApiKey) {
                        cerebrasApiKeyInput.placeholder = 'API key saved';
                    } else {
                        cerebrasApiKeyInput.placeholder = 'Get from cloud.cerebras.com';
                    }
                }
                if (cerebrasModelInput) {
                    const savedModel = settings.cerebras.model || 'llama-3.3-70b-versatile';
                    let modelExists = false;
                    for (let i = 0; i < cerebrasModelInput.options.length; i++) {
                        if (cerebrasModelInput.options[i].value === savedModel) {
                            modelExists = true;
                            break;
                        }
                    }
                    if (!modelExists && savedModel) {
                        const option = document.createElement('option');
                        option.value = savedModel;
                        option.textContent = savedModel;
                        cerebrasModelInput.appendChild(option);
                    }
                    cerebrasModelInput.value = savedModel;
                }
            }
            
            const provider = providerSelect.value;
            lmstudioSettings.style.display = provider === 'lmstudio' ? 'block' : 'none';
            openrouterSettings.style.display = provider === 'openrouter' ? 'block' : 'none';
            if (cerebrasSettings) {
                cerebrasSettings.style.display = provider === 'cerebras' ? 'block' : 'none';
            }
            if (llamacppSettings) {
                llamacppSettings.style.display = provider === 'llamacpp' ? 'block' : 'none';
            }
            
            // Load llama.cpp settings if present
            if (settings.llamacpp) {
                if (llamacppUrlInput) {
                    llamacppUrlInput.value = settings.llamacpp.base_url || 'http://localhost:8080';
                }
                if (llamacppModelInput) {
                    llamacppModelInput.value = settings.llamacpp.model || '';
                }
                if (llamacppDownloadLocation) {
                    llamacppDownloadLocation.value = settings.llamacpp.download_location || 'server';
                }
                if (llamacppAutoStart) {
                    llamacppAutoStart.checked = settings.llamacpp.auto_start || false;
                }
            }
            
            // Load HuggingFace token if present
            if (settings.huggingface) {
                if (huggingfaceTokenInput && settings.huggingface.token) {
                    // Mask the token in the input field
                    const token = settings.huggingface.token;
                    if (token.length > 8) {
                        huggingfaceTokenInput.value = token.substring(0, 4) + '...' + token.slice(-4);
                    } else {
                        huggingfaceTokenInput.value = 'hf_***';
                    }
                }
            }
            
            await loadModels();
            // Note: checkHealth is called after autoStartLlamaCppServer in DOMContentLoaded
            
            if (globalSystemPromptInput && settings.global_system_prompt) {
                globalSystemPromptInput.value = settings.global_system_prompt;
            }
            
            loadSystemPrompt();
        }
    } catch (error) {
        console.error('Error loading settings:', error);
    }
}

// Save settings
async function saveSettingsHandler() {
    const provider = providerSelect.value;
    
    let selectedModel = '';
    if (provider === 'cerebras' && cerebrasModelInput) {
        selectedModel = cerebrasModelInput.value.trim();
    } else if (provider === 'openrouter' && openrouterModelInput) {
        selectedModel = openrouterModelInput.value.trim();
    } else if (provider === 'llamacpp' && llamacppModelInput) {
        selectedModel = llamacppModelInput.value.trim();
        // Save to localStorage for persistence
        if (selectedModel) {
            localStorage.setItem('llamacpp_selected_model', selectedModel);
        }
    }
    
    let currentSettings = {};
    try {
        const response = await fetch('/api/settings');
        const data = await response.json();
        if (data.success) {
            currentSettings = data.settings;
        }
    } catch (e) {
        console.error('Error fetching current settings:', e);
    }
    
    const openrouterKey = openrouterApiKeyInput.value.trim();
    const cerebrasKey = cerebrasApiKeyInput ? cerebrasApiKeyInput.value.trim() : '';
    
    // Check if the key is masked (contains "..." which means it wasn't changed)
    const isOpenRouterMasked = openrouterKey.includes('••••') || openrouterKey === '';
    const isCerebrasMasked = cerebrasKey.includes('...') || (cerebrasKey && cerebrasKey.length < 20);
    
    // Get HF token from settings modal (huggingfaceTokenInput) or LLM Model Manager (hfTokenInput)
    let hfTokenValue = '';
    if (huggingfaceTokenInput) {
        hfTokenValue = huggingfaceTokenInput.value.trim();
    }
    // Also check LLM Model Manager's hfToken if available
    if (!hfTokenValue && hfTokenInput) {
        hfTokenValue = hfTokenInput.value.trim();
    }
    
    const isHfTokenMasked = hfTokenValue.includes('...') || hfTokenValue === '' || hfTokenValue === 'hf_***';
    
    const settings = {
        provider: provider,
        global_system_prompt: globalSystemPromptInput ? globalSystemPromptInput.value : '',
        lmstudio: {
            base_url: lmstudioUrlInput.value,
            direct: lmstudioDirectInput ? lmstudioDirectInput.checked : false
        },
        openrouter: {
            api_key: !isOpenRouterMasked ? openrouterKey : (currentSettings.openrouter?.api_key || ''),
            model: selectedModel || openrouterModelInput.value,
            context_size: parseInt(openrouterContextInput.value) || 128000,
            thinking_budget: parseInt(openrouterThinkingInput.value) || 0
        },
        cerebras: {
            api_key: !isCerebrasMasked ? cerebrasKey : (currentSettings.cerebras?.api_key || ''),
            model: selectedModel || 'llama-3.3-70b-versatile'
        },
        llamacpp: {
            base_url: llamacppUrlInput ? llamacppUrlInput.value : 'http://localhost:8080',
            model: llamacppModelInput ? llamacppModelInput.value : '',
            download_location: llamacppDownloadLocation ? llamacppDownloadLocation.value : 'server',
            auto_start: llamacppAutoStart ? llamacppAutoStart.checked : false
        },
        huggingface: {
            token: !isHfTokenMasked ? hfTokenValue : (currentSettings.huggingface?.token || '')
        }
    };
    
    console.log('Saving settings:', settings);
    await saveSystemPromptHandler();
    
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        if (!response.ok) {
            const text = await response.text();
            console.error('Server error:', response.status, text);
            alert('Error saving settings: ' + response.status);
            return;
        }
        
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            console.error('Non-JSON response:', contentType);
            alert('Server returned an error. Make sure the chatbot server is running.');
            return;
        }
        
        const data = await response.json();
        
        if (data.success) {
            settingsModal.classList.remove('active');
            
            if (provider === 'cerebras' && cerebrasModelInput && cerebrasModelInput.options.length > 0) {
                const cerebrasModels = [];
                for (let i = 0; i < cerebrasModelInput.options.length; i++) {
                    cerebrasModels.push(cerebrasModelInput.options[i].value);
                }
                
                modelSelect.innerHTML = '';
                cerebrasModels.forEach(m => {
                    const option = document.createElement('option');
                    option.value = m.id;
                    option.textContent = m.name || m.id;
                    modelSelect.appendChild(option);
                });
                
                if (selectedModel && cerebrasModels.includes(selectedModel)) {
                    modelSelect.value = selectedModel;
                } else if (cerebrasModels.length > 0) {
                    modelSelect.value = cerebrasModels[0];
                }
                
                console.log('Updated model dropdown with Cerebras models:', cerebrasModels);
            } else {
                await loadModels();
            }
            
            await checkHealth();
        } else {
            alert('Error: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error saving settings:', error);
        alert('Failed to connect to server. Make sure the chatbot is running.');
    }
}

// Load OpenRouter models
async function loadOpenRouterModels() {
    loadOpenRouterModelsBtn.textContent = 'Loading...';
    loadOpenRouterModelsBtn.disabled = true;
    
    const settings = {
        provider: 'openrouter',
        openrouter: {
            api_key: openrouterApiKeyInput.value,
            model: openrouterModelInput.value
        }
    };
    
    try {
        await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        const response = await fetch('/api/openrouter/models');
        const data = await response.json();
        
        if (data.success && data.models) {
            openrouterModelInput.innerHTML = '';
            data.models.forEach(m => {
                const option = document.createElement('option');
                option.value = m.id;
                option.textContent = m.name || m.id;
                openrouterModelInput.appendChild(option);
            });
        } else {
            alert('Error loading models: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        alert('Error loading models: ' + error.message);
    } finally {
        loadOpenRouterModelsBtn.textContent = 'Load Models';
        loadOpenRouterModelsBtn.disabled = false;
    }
}

// Load OpenAI Compatible models
async function loadOpenAiCompatibleModels() {
    const apiKey = openaiCompatibleApiKey.value.trim();
    const baseUrl = openaiCompatibleUrl.value.trim();
    
    if (!apiKey) {
        alert('Please enter your OpenAI-compatible API key first');
        return;
    }
    
    if (!baseUrl) {
        alert('Please enter your OpenAI-compatible API base URL first');
        return;
    }
    
    loadOpenAiCompatibleModelsBtn.textContent = 'Loading...';
    loadOpenAiCompatibleModelsBtn.disabled = true;
    
    const settings = {
        provider: 'openai_compatible',
        openai_compatible: {
            api_key: apiKey,
            base_url: baseUrl,
            model: openaiCompatibleModel.value
        }
    };
    
    try {
        await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        const response = await fetch('/api/openai_compatible/models');
        const data = await response.json();
        
        if (data.success && data.models) {
            openaiCompatibleModel.innerHTML = '';
            data.models.forEach(m => {
                const option = document.createElement('option');
                option.value = m.id || m;
                option.textContent = m.name || m.id || m;
                openaiCompatibleModel.appendChild(option);
            });
            loadOpenAiCompatibleModelsBtn.textContent = 'Models Loaded!';
        } else {
            alert('Error loading models: ' + (data.error || 'Unknown error'));
            loadOpenAiCompatibleModelsBtn.textContent = 'Load Models';
        }
    } catch (error) {
        alert('Error loading models: ' + error.message);
        loadOpenAiCompatibleModelsBtn.textContent = 'Load Models';
    } finally {
        loadOpenAiCompatibleModelsBtn.disabled = false;
    }
}

// Load Cerebras models
async function loadCerebrasModels() {
    if (!loadCerebrasModelsBtn) return;
    
    const apiKey = cerebrasApiKeyInput.value.trim();
    if (!apiKey) {
        alert('Please enter your Cerebras API key first');
        return;
    }
    
    loadCerebrasModelsBtn.textContent = 'Loading...';
    loadCerebrasModelsBtn.disabled = true;
    
    const settings = {
        provider: 'cerebras',
        cerebras: {
            api_key: apiKey,
            model: ''
        }
    };
    
    try {
        await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        const response = await fetch('/api/models');
        const data = await response.json();
        
        if (data.success && data.models) {
            cerebrasModelInput.innerHTML = '';
            
            // Handle different model formats
            data.models.forEach(m => {
                const option = document.createElement('option');
                
                // Check if model is an object with id/name properties
                if (typeof m === 'object' && m !== null) {
                    option.value = m.id || m.name || m;
                    option.textContent = m.name || m.id || m;
                } else {
                    // Model is a string
                    option.value = m;
                    option.textContent = m;
                }
                
                cerebrasModelInput.appendChild(option);
            });
            
            loadCerebrasModelsBtn.textContent = 'Models Loaded!';
        } else {
            alert('Error loading models: ' + (data.error || 'Unknown error'));
            loadCerebrasModelsBtn.textContent = 'Load Models';
        }
    } catch (error) {
        alert('Error loading models: ' + error.message);
        loadCerebrasModelsBtn.textContent = 'Load Models';
    } finally {
        loadCerebrasModelsBtn.disabled = false;
    }
}

// Load Cerebras settings to show saved API key
async function loadCerebrasSettings() {
    try {
        const response = await fetch('/api/settings');
        const data = await response.json();
        
        if (data.success && data.settings && data.settings.cerebras) {
            const settings = data.settings.cerebras;
            
            if (cerebrasApiKeyInput) {
                const storedApiKey = settings.api_key;
                if (storedApiKey && storedApiKey.length > 4) {
                    // Show masked key in the input field (first 8 chars + ...)
                    const maskedKey = storedApiKey.substring(0, 8) + '...' + storedApiKey.slice(-4);
                    cerebrasApiKeyInput.value = maskedKey;
                } else if (storedApiKey) {
                    cerebrasApiKeyInput.placeholder = 'API key saved';
                } else {
                    cerebrasApiKeyInput.placeholder = 'Get from cloud.cerebras.com';
                }
            }
            
            if (cerebrasModelInput) {
                const savedModel = settings.model || 'llama-3.3-70b-versatile';
                let modelExists = false;
                for (let i = 0; i < cerebrasModelInput.options.length; i++) {
                    if (cerebrasModelInput.options[i].value === savedModel) {
                        modelExists = true;
                        break;
                    }
                }
                if (!modelExists && savedModel) {
                    const option = document.createElement('option');
                    option.value = savedModel;
                    option.textContent = savedModel;
                    cerebrasModelInput.appendChild(option);
                }
                cerebrasModelInput.value = savedModel;
            }
        }
    } catch (error) {
        console.error('Error loading Cerebras settings:', error);
    }
}

// Load OpenRouter settings to show saved API key
async function loadOpenRouterSettings() {
    try {
        const response = await fetch('/api/settings');
        const data = await response.json();
        
        if (data.success && data.settings && data.settings.openrouter) {
            const settings = data.settings.openrouter;
            
            if (openrouterApiKeyInput) {
                const storedApiKey = settings.api_key;
                if (storedApiKey && storedApiKey.length > 4) {
                    openrouterApiKeyInput.placeholder = '••••' + storedApiKey.slice(-4);
                } else if (storedApiKey) {
                    openrouterApiKeyInput.placeholder = 'API key saved';
                } else {
                    openrouterApiKeyInput.placeholder = 'sk-or-...';
                }
            }
            
            if (openrouterModelInput) {
                openrouterModelInput.value = settings.model || 'openai/gpt-4o-mini';
            }
            
            if (openrouterContextInput) {
                openrouterContextInput.value = settings.context_size || 128000;
            }
            
            if (openrouterThinkingInput) {
                openrouterThinkingInput.value = settings.thinking_budget || 0;
            }
        }
    } catch (error) {
        console.error('Error loading OpenRouter settings:', error);
    }
}

// Load TTS speakers
async function loadTTSSpeakers() {
    try {
        const response = await fetch('/api/tts/speakers');
        const data = await response.json();
        
        if (data.success && data.speakers) {
            ttsSpeaker.innerHTML = '';
            
            data.speakers.forEach(speaker => {
                const option = document.createElement('option');
                option.value = speaker.id;
                option.textContent = speaker.name || speaker.id;
                ttsSpeaker.appendChild(option);
            });
            
            // Load saved speaker from localStorage, default to Maya for new users
            const savedSpeaker = localStorage.getItem('selectedSpeaker');
            if (savedSpeaker) {
                // Check if saved speaker exists in the list
                const speakerExists = data.speakers.some(s => s.id === savedSpeaker);
                if (speakerExists) {
                    ttsSpeaker.value = savedSpeaker;
                } else {
                    // Default to Maya if saved speaker doesn't exist
                    const mayaExists = data.speakers.some(s => s.id === 'Maya' || s.name === 'Maya');
                    ttsSpeaker.value = mayaExists ? 'Maya' : (data.speakers[0]?.id || '');
                }
            } else {
                // New user - default to Maya
                const mayaExists = data.speakers.some(s => s.id === 'Maya' || s.name === 'Maya');
                ttsSpeaker.value = mayaExists ? 'Maya' : (data.speakers[0]?.id || '');
            }
        }
    } catch (error) {
        console.error('Error loading TTS speakers:', error);
    }
}

// Check provider connection
async function checkHealth() {
    try {
        const response = await fetch('/api/health');
        const data = await response.json();
        
        if (data.status === 'connected') {
            statusDot.className = 'status-dot connected';
            if (data.provider === 'cerebras') {
                statusText.textContent = 'Cerebras';
            } else if (data.provider === 'openrouter') {
                statusText.textContent = 'OpenRouter';
            } else {
                statusText.textContent = 'Connected';
            }
            sendBtn.disabled = !messageInput.value.trim();
        } else {
            statusDot.className = 'status-dot disconnected';
            statusText.textContent = data.message || 'Disconnected';
            sendBtn.disabled = true;
        }
    } catch (error) {
        statusDot.className = 'status-dot disconnected';
        statusText.textContent = 'Disconnected';
        sendBtn.disabled = true;
    }
}

// Load available models
async function loadModels() {
    try {
        const response = await fetch('/api/models');
        const data = await response.json();
        
        modelSelect.innerHTML = '';
        
        if (data.success && data.models && data.models.length > 0) {
            data.models.forEach(model => {
                const option = document.createElement('option');
                // Handle both string and object models
                if (typeof model === 'object' && model !== null) {
                    option.value = model.id || model.name || model;
                    option.textContent = model.name || model.id || model;
                } else {
                    option.value = model;
                    option.textContent = model;
                }
                modelSelect.appendChild(option);
            });
            
            // Get the selected model from settings.json for the current provider
            let selectedModelFromSettings = '';
            try {
                const settingsResponse = await fetch('/api/settings');
                const settingsData = await settingsResponse.json();
                if (settingsData.success && settingsData.settings) {
                    const provider = settingsData.settings.provider;
                    if (provider === 'cerebras' && settingsData.settings.cerebras?.model) {
                        selectedModelFromSettings = settingsData.settings.cerebras.model;
                    } else if (provider === 'openrouter' && settingsData.settings.openrouter?.model) {
                        selectedModelFromSettings = settingsData.settings.openrouter.model;
                    } else if (provider === 'llamacpp' && settingsData.settings.llamacpp?.model) {
                        selectedModelFromSettings = settingsData.settings.llamacpp.model;
                    }
                }
            } catch (error) {
                console.error('Error fetching settings for model selection:', error);
            }
            
            // Select the model from settings if it exists in the list, otherwise select the first model
            if (selectedModelFromSettings) {
                // Handle both string and object models for selection
                let modelExists = false;
                if (typeof selectedModelFromSettings === 'object' && selectedModelFromSettings !== null) {
                    // If settings contains an object, try to match by id or name
                    for (let i = 0; i < data.models.length; i++) {
                        const model = data.models[i];
                        if (typeof model === 'object' && model !== null) {
                            if (model.id === selectedModelFromSettings.id || model.name === selectedModelFromSettings.name) {
                                modelSelect.value = model.id || model.name || model;
                                modelExists = true;
                                break;
                            }
                        }
                    }
                } else {
                    // If settings contains a string, try to match by value
                    for (let i = 0; i < data.models.length; i++) {
                        const model = data.models[i];
                        if (typeof model === 'object' && model !== null) {
                            if (model.id === selectedModelFromSettings || model.name === selectedModelFromSettings) {
                                modelSelect.value = model.id || model.name || model;
                                modelExists = true;
                                break;
                            }
                        } else if (model === selectedModelFromSettings) {
                            modelSelect.value = model;
                            modelExists = true;
                            break;
                        }
                    }
                }
                
                if (!modelExists && data.models.length > 0) {
                    // If the saved model doesn't exist, select the first one
                    const firstModel = data.models[0];
                    if (typeof firstModel === 'object' && firstModel !== null) {
                        modelSelect.value = firstModel.id || firstModel.name || firstModel;
                    } else {
                        modelSelect.value = firstModel;
                    }
                }
            } else if (data.models.length > 0) {
                // No saved model, select the first one
                const firstModel = data.models[0];
                if (typeof firstModel === 'object' && firstModel !== null) {
                    modelSelect.value = firstModel.id || firstModel.name || firstModel;
                } else {
                    modelSelect.value = firstModel;
                }
            }
        } else {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'No models available';
            modelSelect.appendChild(option);
        }
    } catch (error) {
        console.error('Error loading models:', error);
        modelSelect.innerHTML = '<option value="">Error loading models</option>';
    }
}

// Scroll to bottom
function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// Render markdown
function renderMarkdown(text) {
    if (typeof marked !== 'undefined') {
        return marked.parse(text);
    }
    return text.replace(/\n/g, '<br>');
}

// Copy to clipboard
function copyToClipboard(text, button) {
    navigator.clipboard.writeText(text).then(() => {
        button.textContent = 'Copied!';
        button.classList.add('copied');
        setTimeout(() => {
            button.textContent = 'Copy';
            button.classList.remove('copied');
        }, 2000);
    });
}

// ==================== LLM MODEL MANAGER ====================

// LLM Model Manager DOM Elements
const llmModelBtn = document.getElementById('llmModelBtn');
const llmModelModal = document.getElementById('llmModelModal');
const closeLlmModel = document.getElementById('closeLlmModel');
const modelDownloadUrl = document.getElementById('modelDownloadUrl');
const modelPageUrl = document.getElementById('modelPageUrl');
const fetchFilesBtn = document.getElementById('fetchFilesBtn');
const ggufFilesGroup = document.getElementById('ggufFilesGroup');
const ggufFilesSelect = document.getElementById('ggufFilesSelect');
const downloadSelectedBtn = document.getElementById('downloadSelectedBtn');
const startDownloadBtn = document.getElementById('startDownloadBtn');
const downloadProgress = document.getElementById('downloadProgress');
const downloadFilename = document.getElementById('downloadFilename');
const downloadStatus = document.getElementById('downloadStatus');
const downloadProgressBar = document.getElementById('downloadProgressBar');
const downloadSpeed = document.getElementById('downloadSpeed');
const downloadEta = document.getElementById('downloadEta');
const downloadPercent = document.getElementById('downloadPercent');
const pauseDownloadBtn = document.getElementById('pauseDownloadBtn');
const resumeDownloadBtn = document.getElementById('resumeDownloadBtn');
const stopDownloadBtn = document.getElementById('stopDownloadBtn');
const llmModelsList = document.getElementById('llmModelsList');

// Store fetched files for download
let fetchedGgufFiles = [];

// Download state
let currentDownloadId = null;
let downloadStatusInterval = null;

// Fetch files from HuggingFace model page
if (fetchFilesBtn) {
    fetchFilesBtn.addEventListener('click', async () => {
        const url = modelPageUrl.value.trim();
        
        if (!url) {
            alert('Please enter a HuggingFace model page URL');
            return;
        }
        
        // Basic URL validation
        if (!url.includes('huggingface.co')) {
            alert('Please enter a valid HuggingFace URL (e.g., https://huggingface.co/ggml-org/Devstral-Small-2-24B-Instruct-2512-GGUF)');
            return;
        }
        
        fetchFilesBtn.disabled = true;
        fetchFilesBtn.textContent = 'Fetching...';
        
        try {
            const response = await fetch('/api/llm/huggingface/files', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model_url: url })
            });
            
            const data = await response.json();
            
            if (data.success) {
                fetchedGgufFiles = data.files || [];
                
                if (fetchedGgufFiles.length === 0) {
                    alert('No GGUF files found for this model.');
                    ggufFilesGroup.style.display = 'none';
                    return;
                }
                
                // Populate dropdown
                ggufFilesSelect.innerHTML = '<option value="">-- Select a file to download --</option>';
                
                fetchedGgufFiles.forEach((file, index) => {
                    const option = document.createElement('option');
                    option.value = index;  // Use index to reference the file
                    option.textContent = `${file.name} (${file.size_formatted})`;
                    ggufFilesSelect.appendChild(option);
                });
                
                // Show the dropdown
                ggufFilesGroup.style.display = 'block';
            } else {
                alert('Error fetching files: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error fetching files:', error);
            alert('Error fetching files. Make sure the URL is correct.');
        } finally {
            fetchFilesBtn.disabled = false;
            fetchFilesBtn.textContent = 'Fetch Files';
        }
    });
}

// Download selected file from dropdown
if (downloadSelectedBtn) {
    downloadSelectedBtn.addEventListener('click', async () => {
        const selectedIndex = ggufFilesSelect.value;
        
        if (selectedIndex === '') {
            alert('Please select a file to download');
            return;
        }
        
        const file = fetchedGgufFiles[selectedIndex];
        if (!file || !file.download_url) {
            alert('Invalid file selection');
            return;
        }
        
        downloadSelectedBtn.disabled = true;
        downloadSelectedBtn.textContent = 'Starting...';
        
        try {
            const response = await fetch('/api/llm/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: file.download_url })
            });
            
            const data = await response.json();
            
            if (data.success) {
                currentDownloadId = data.download_id;
                downloadProgress.style.display = 'block';
                downloadFilename.textContent = data.filename;
                downloadStatus.textContent = 'Starting...';
                downloadProgressBar.style.width = '0%';
                downloadPercent.textContent = '0%';
                downloadSpeed.textContent = '0 MB/s';
                downloadEta.textContent = '--:--';
                
                // Start polling for status
                downloadStatusInterval = setInterval(updateDownloadStatus, 1000);
            } else {
                alert('Error starting download: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error starting download:', error);
            alert('Error starting download');
        } finally {
            downloadSelectedBtn.disabled = false;
            downloadSelectedBtn.textContent = 'Download Selected';
        }
    });
}

// Setup LLM Model Manager
if (llmModelBtn) {
    llmModelBtn.addEventListener('click', () => {
        llmModelModal.classList.add('active');
        loadLlmModels();
    });
}

if (closeLlmModel) {
    closeLlmModel.addEventListener('click', () => {
        llmModelModal.classList.remove('active');
    });
}

if (llmModelModal) {
    llmModelModal.addEventListener('click', (e) => {
        if (e.target === llmModelModal) {
            llmModelModal.classList.remove('active');
        }
    });
}

// Load LLM models list
async function loadLlmModels() {
    try {
        const response = await fetch('/api/llm/models');
        const data = await response.json();
        
        if (data.success && data.models) {
            if (data.models.length === 0) {
                llmModelsList.innerHTML = '<p style="color: var(--text-muted);">No models installed. Download a GGUF model to get started.</p>';
            } else {
                llmModelsList.innerHTML = '';
                data.models.forEach(model => {
                    const modelItem = document.createElement('div');
                    modelItem.className = 'llm-model-item';
                    modelItem.innerHTML = `
                        <div class="model-info">
                            <span class="model-name">${model.name}</span>
                            <span class="model-size">${model.size_formatted}</span>
                        </div>
                        <button class="delete-model-btn" onclick="deleteLlmModel('${model.name}')" title="Delete model">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                                <path d="M3 6H5H21" stroke="currentColor" stroke-width="2"/>
                                <path d="M19 6V20C19 21 18 22 17 22H7C6 22 5 21 5 20V6" stroke="currentColor" stroke-width="2"/>
                            </svg>
                        </button>
                    `;
                    llmModelsList.appendChild(modelItem);
                });
            }
        } else {
            llmModelsList.innerHTML = '<p style="color: var(--text-muted);">Error loading models.</p>';
        }
    } catch (error) {
        console.error('Error loading LLM models:', error);
        llmModelsList.innerHTML = '<p style="color: var(--text-muted);">Error loading models.</p>';
    }
}

// Delete LLM model
async function deleteLlmModel(filename) {
    if (!confirm(`Delete model "${filename}"? This cannot be undone.`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/llm/models/${encodeURIComponent(filename)}`, {
            method: 'DELETE'
        });
        const data = await response.json();
        
        if (data.success) {
            loadLlmModels();
        } else {
            alert('Error deleting model: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error deleting model:', error);
        alert('Error deleting model');
    }
}

// Start download
if (startDownloadBtn) {
    startDownloadBtn.addEventListener('click', async () => {
        const url = modelDownloadUrl.value.trim();
        
        if (!url) {
            alert('Please enter a HuggingFace download URL');
            return;
        }
        
        startDownloadBtn.disabled = true;
        startDownloadBtn.textContent = 'Starting...';
        
        try {
            const response = await fetch('/api/llm/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url })
            });
            
            const data = await response.json();
            
            if (data.success) {
                currentDownloadId = data.download_id;
                downloadProgress.style.display = 'block';
                downloadFilename.textContent = data.filename;
                downloadStatus.textContent = 'Starting...';
                downloadProgressBar.style.width = '0%';
                downloadPercent.textContent = '0%';
                downloadSpeed.textContent = '0 MB/s';
                downloadEta.textContent = '--:--';
                
                // Start polling for status
                downloadStatusInterval = setInterval(updateDownloadStatus, 1000);
            } else {
                alert('Error starting download: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error starting download:', error);
            alert('Error starting download');
        } finally {
            startDownloadBtn.disabled = false;
            startDownloadBtn.textContent = 'Download Model';
        }
    });
}

// Update download status
async function updateDownloadStatus() {
    if (!currentDownloadId) return;
    
    try {
        const response = await fetch(`/api/llm/download/status?id=${currentDownloadId}`);
        const data = await response.json();
        
        if (data.success && data.download) {
            const download = data.download;
            
            downloadFilename.textContent = download.filename;
            downloadProgressBar.style.width = download.progress + '%';
            downloadPercent.textContent = download.progress + '%';
            
            // Update status text
            const statusMap = {
                'starting': 'Starting...',
                'downloading': 'Downloading...',
                'paused': 'Paused',
                'completed': 'Completed!',
                'error': 'Error: ' + (download.error || 'Unknown'),
                'cancelled': 'Cancelled'
            };
            downloadStatus.textContent = statusMap[download.status] || download.status;
            
            // Update speed and ETA
            if (download.speed !== undefined && download.speed !== null) {
                const speedMB = download.speed / (1024 * 1024);
                downloadSpeed.textContent = speedMB.toFixed(2) + ' MB/s';
            }
            
            if (download.eta !== undefined && download.eta !== null && !isNaN(download.eta)) {
                const etaSeconds = Math.round(download.eta);
                const mins = Math.floor(etaSeconds / 60);
                const secs = etaSeconds % 60;
                downloadEta.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
            }
            
            // Update button states
            if (download.status === 'paused') {
                pauseDownloadBtn.style.display = 'none';
                resumeDownloadBtn.style.display = 'inline-block';
            } else if (download.status === 'downloading') {
                pauseDownloadBtn.style.display = 'inline-block';
                resumeDownloadBtn.style.display = 'none';
            }
            
            // Handle completion
            if (download.status === 'completed' || download.status === 'error' || download.status === 'cancelled') {
                clearInterval(downloadStatusInterval);
                
                if (download.status === 'completed') {
                    setTimeout(() => {
                        alert('Download completed successfully!');
                        downloadProgress.style.display = 'none';
                        modelDownloadUrl.value = '';
                        loadLlmModels();
                    }, 500);
                } else if (download.status === 'error') {
                    setTimeout(() => {
                        alert('Download error: ' + (download.error || 'Unknown error'));
                        downloadProgress.style.display = 'none';
                    }, 500);
                }
            }
        }
    } catch (error) {
        console.error('Error updating download status:', error);
    }
}

// Pause download
if (pauseDownloadBtn) {
    pauseDownloadBtn.addEventListener('click', async () => {
        try {
            await fetch('/api/llm/download/pause', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ download_id: currentDownloadId })
            });
        } catch (error) {
            console.error('Error pausing download:', error);
        }
    });
}

// Resume download
if (resumeDownloadBtn) {
    resumeDownloadBtn.addEventListener('click', async () => {
        try {
            await fetch('/api/llm/download/resume', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ download_id: currentDownloadId })
            });
        } catch (error) {
            console.error('Error resuming download:', error);
        }
    });
}

// Stop download
if (stopDownloadBtn) {
    stopDownloadBtn.addEventListener('click', async () => {
        if (!confirm('Stop download? The partial file will be deleted.')) {
            return;
        }
        
        try {
            await fetch('/api/llm/download/stop', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ download_id: currentDownloadId })
            });
            
            clearInterval(downloadStatusInterval);
            downloadProgress.style.display = 'none';
            currentDownloadId = null;
        } catch (error) {
            console.error('Error stopping download:', error);
        }
    });
}

// ==================== LLAMA.CPP SETTINGS MODEL LOADING ====================

// llama.cpp Settings DOM Elements
const llamacppDownloadUrl = document.getElementById('llamacppDownloadUrl');
const llamacppDownloadBtn = document.getElementById('llamacppDownloadBtn');
const llamacppDownloadProgress = document.getElementById('llamacppDownloadProgress');
const llamacppDownloadFilename = document.getElementById('llamacppDownloadFilename');
const llamacppDownloadStatus = document.getElementById('llamacppDownloadStatus');
const llamacppDownloadProgressBar = document.getElementById('llamacppDownloadProgressBar');
const llamacppDownloadSpeed = document.getElementById('llamacppDownloadSpeed');
const llamacppDownloadEta = document.getElementById('llamacppDownloadEta');
const llamacppDownloadPercent = document.getElementById('llamacppDownloadPercent');
const llamacppPauseDownloadBtn = document.getElementById('llamacppPauseDownloadBtn');
const llamacppResumeDownloadBtn = document.getElementById('llamacppResumeDownloadBtn');
const llamacppStopDownloadBtn = document.getElementById('llamacppStopDownloadBtn');

// llama.cpp download state
let llamacppCurrentDownloadId = null;
let llamacppDownloadStatusInterval = null;

// Load LLM models into llama.cpp dropdown
async function loadLlmModelsForLlamaCpp() {
    try {
        // Check localStorage first, then current value, then settings
        let userSelectedModel = localStorage.getItem('llamacpp_selected_model');
        if (!userSelectedModel || userSelectedModel === "") {
            userSelectedModel = llamacppModelInput.value;
        }
        
        const response = await fetch('/api/llm/models');
        const data = await response.json();
        
        if (data.success && data.models) {
            // Clear existing options except first
            llamacppModelInput.innerHTML = '<option value="">-- Select a model --</option>';
            
            data.models.forEach(model => {
                const option = document.createElement('option');
                option.value = model.name;
                option.textContent = `${model.name} (${model.size_formatted})`;
                llamacppModelInput.appendChild(option);
            });
            
            // Restore user selection if exists, otherwise load from settings
            if (userSelectedModel && userSelectedModel !== "") {
                const optionExists = Array.from(llamacppModelInput.options).some(option => option.value === userSelectedModel);
                if (optionExists) {
                    llamacppModelInput.value = userSelectedModel;
                } else {
                    // User selection doesn't exist in new list, add it temporarily
                    const tempOption = document.createElement('option');
                    tempOption.value = userSelectedModel;
                    tempOption.textContent = `${userSelectedModel} (selected)`;
                    llamacppModelInput.appendChild(tempOption);
                    llamacppModelInput.value = userSelectedModel;
                }
            } else {
                // Load saved model from settings
                const settingsResponse = await fetch('/api/settings');
                const settingsData = await settingsResponse.json();
                if (settingsData.success && settingsData.settings.llamacpp?.model) {
                    const savedModel = settingsData.settings.llamacpp.model;
                    // Check if the saved model exists in the dropdown
                    const optionExists = Array.from(llamacppModelInput.options).some(option => option.value === savedModel);
                    if (optionExists) {
                        llamacppModelInput.value = savedModel;
                    } else {
                        // If the option doesn't exist yet, add it temporarily
                        // This can happen if models are still loading
                        const tempOption = document.createElement('option');
                        tempOption.value = savedModel;
                        tempOption.textContent = `${savedModel} (saved)`;
                        llamacppModelInput.appendChild(tempOption);
                        llamacppModelInput.value = savedModel;
                    }
                }
            }
        }
    } catch (error) {
        console.error('Error loading LLM models for llama.cpp:', error);
    }
}

// Setup llama.cpp download
if (llamacppDownloadBtn) {
    llamacppDownloadBtn.addEventListener('click', async () => {
        const url = llamacppDownloadUrl.value.trim();
        
        if (!url) {
            alert('Please enter a HuggingFace download URL');
            return;
        }
        
        llamacppDownloadBtn.disabled = true;
        llamacppDownloadBtn.textContent = 'Starting...';
        
        try {
            const response = await fetch('/api/llm/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: url })
            });
            
            const data = await response.json();
            
            if (data.success) {
                llamacppCurrentDownloadId = data.download_id;
                llamacppDownloadProgress.style.display = 'block';
                llamacppDownloadFilename.textContent = data.filename;
                llamacppDownloadStatus.textContent = 'Starting...';
                llamacppDownloadProgressBar.style.width = '0%';
                llamacppDownloadPercent.textContent = '0%';
                llamacppDownloadSpeed.textContent = '0 MB/s';
                llamacppDownloadEta.textContent = '--:--';
                
                // Start polling for status
                llamacppDownloadStatusInterval = setInterval(updateLlamaCppDownloadStatus, 1000);
            } else {
                alert('Error starting download: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error starting download:', error);
            alert('Error starting download');
        } finally {
            llamacppDownloadBtn.disabled = false;
            llamacppDownloadBtn.textContent = 'Download Model';
        }
    });
}

// Update llama.cpp download status
async function updateLlamaCppDownloadStatus() {
    if (!llamacppCurrentDownloadId) return;
    
    try {
        const response = await fetch(`/api/llm/download/status?id=${llamacppCurrentDownloadId}`);
        const data = await response.json();
        
        if (data.success && data.download) {
            const download = data.download;
            
            llamacppDownloadFilename.textContent = download.filename;
            llamacppDownloadProgressBar.style.width = download.progress + '%';
            llamacppDownloadPercent.textContent = download.progress + '%';
            
            // Update status text
            const statusMap = {
                'starting': 'Starting...',
                'downloading': 'Downloading...',
                'paused': 'Paused',
                'completed': 'Completed!',
                'error': 'Error: ' + (download.error || 'Unknown'),
                'cancelled': 'Cancelled'
            };
            llamacppDownloadStatus.textContent = statusMap[download.status] || download.status;
            
            // Update speed and ETA
            if (download.speed !== undefined && download.speed !== null) {
                const speedMB = download.speed / (1024 * 1024);
                llamacppDownloadSpeed.textContent = speedMB.toFixed(2) + ' MB/s';
            }
            
            if (download.eta !== undefined && download.eta !== null && !isNaN(download.eta)) {
                const etaSeconds = Math.round(download.eta);
                const mins = Math.floor(etaSeconds / 60);
                const secs = etaSeconds % 60;
                llamacppDownloadEta.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
            }
            
            // Update button states
            if (download.status === 'paused') {
                llamacppPauseDownloadBtn.style.display = 'none';
                llamacppResumeDownloadBtn.style.display = 'inline-block';
            } else if (download.status === 'downloading') {
                llamacppPauseDownloadBtn.style.display = 'inline-block';
                llamacppResumeDownloadBtn.style.display = 'none';
            }
            
            // Handle completion
            if (download.status === 'completed' || download.status === 'error' || download.status === 'cancelled') {
                clearInterval(llamacppDownloadStatusInterval);
                
                if (download.status === 'completed') {
                    setTimeout(() => {
                        alert('Download completed successfully!');
                        llamacppDownloadProgress.style.display = 'none';
                        llamacppDownloadUrl.value = '';
                        loadLlmModelsForLlamaCpp();
                    }, 500);
                } else if (download.status === 'error') {
                    setTimeout(() => {
                        alert('Download error: ' + (download.error || 'Unknown error'));
                        llamacppDownloadProgress.style.display = 'none';
                    }, 500);
                }
            }
        }
    } catch (error) {
        console.error('Error updating llama.cpp download status:', error);
    }
}

// Pause llama.cpp download
if (llamacppPauseDownloadBtn) {
    llamacppPauseDownloadBtn.addEventListener('click', async () => {
        try {
            await fetch('/api/llm/download/pause', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ download_id: llamacppCurrentDownloadId })
            });
        } catch (error) {
            console.error('Error pausing download:', error);
        }
    });
}

// Resume llama.cpp download
if (llamacppResumeDownloadBtn) {
    llamacppResumeDownloadBtn.addEventListener('click', async () => {
        try {
            await fetch('/api/llm/download/resume', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ download_id: llamacppCurrentDownloadId })
            });
        } catch (error) {
            console.error('Error resuming download:', error);
        }
    });
}

if (llamacppStopDownloadBtn) {
    llamacppStopDownloadBtn.addEventListener('click', async () => {
        if (!confirm('Stop download? The partial file will be deleted.')) {
            return;
        }
        
        try {
            await fetch('/api/llm/download/stop', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ download_id: llamacppCurrentDownloadId })
            });
            
            clearInterval(llamacppDownloadStatusInterval);
            llamacppDownloadProgress.style.display = 'none';
            llamacppCurrentDownloadId = null;
        } catch (error) {
            console.error('Error stopping download:', error);
        }
    });
}

// Suppress XMLHttpRequest 503/404 errors in console (normal during server startup)
const originalXHR = window.XMLHttpRequest;
window.XMLHttpRequest = function() {
    const xhr = new originalXHR();
    
    // Store original open and send
    const originalOpen = xhr.open.bind(xhr);
    const originalSend = xhr.send.bind(xhr);
    
    xhr.open = function() {
        // Store the URL for later filtering
        this._xhrUrl = arguments[0];
        return originalOpen.apply(this, arguments);
    };
    
    // Override send to intercept errors for localhost:8080
    xhr.send = function() {
        const url = this._xhrUrl || '';
        
        // Check if this is a llama.cpp server check
        const isLlamaCppCheck = url.includes('localhost:8080') && url.includes('/v1/models');
        
        if (isLlamaCppCheck) {
            // Override onload and onerror for silent handling
            const originalOnload = this.onload;
            const originalOnerror = this.onerror;
            const originalOntimeout = this.ontimeout;
            
            this.onload = function(e) {
                // Only suppress 503/404 for llama.cpp server checks
                if (this.status === 503 || this.status === 404) {
                    // Don't log error, but still call original onload if exists
                    if (originalOnload) {
                        // Create a fake event that indicates success for retry logic
                        const fakeEvent = { 
                            target: this, 
                            type: 'load',
                            loaded: true
                        };
                        originalOnload.call(this, fakeEvent);
                    }
                    return;
                }
                if (originalOnload) originalOnload.call(this, e);
            };
            
            this.onerror = function(e) {
                // Don't propagate network errors for llama.cpp checks
                // Let the timeout handle it
            };
            
            this.ontimeout = function(e) {
                if (originalOntimeout) originalOntimeout.call(this, e);
            };
        }
        
        return originalSend.apply(this, arguments);
    };
    
    return xhr;
};

// Enhanced llama.cpp connection polling with longer wait times
let llamaCppPollingAttempts = 0;
let llamaCppPollingMaxAttempts = 120; // 2 minutes (120 * 1 second)
let llamaCppPollingInterval = null;

function pollLlamaCppServer() {
    if (llamaCppPollingInterval) {
        clearInterval(llamaCppPollingInterval);
    }
    
    llamaCppPollingAttempts = 0;
    
    llamaCppPollingInterval = setInterval(async () => {
        try {
            const response = await fetch('/api/llamacpp/server/status');
            const data = await response.json();
            
            if (data.success && data.running) {
                console.log('[LLAMA.CPP] Server is ready, stopping polling');
                clearInterval(llamacppPollingInterval);
                llamaCppPollingInterval = null;
                
                // Update status indicator
                if (statusDot) {
                    statusDot.className = 'status-dot connected';
                    statusText.textContent = 'llama.cpp';
                }
                
                // Check health to update provider status
                await checkHealth();
                return;
            }
        } catch (error) {
            console.log('[LLAMA.CPP] Server not ready yet, attempts:', llamaCppPollingAttempts + 1);
        }
        
        llamaCppPollingAttempts++;
        
        if (llamaCppPollingAttempts >= llamaCppPollingMaxAttempts) {
            console.log('[LLAMA.CPP] Max polling attempts reached, stopping');
            clearInterval(llamacppPollingInterval);
            llamaCppPollingInterval = null;
            
            // Update status to show server is starting
            if (statusDot) {
                statusDot.className = 'status-dot connecting';
                statusText.textContent = 'llama.cpp (starting...)';
            }
        }
    }, 1000); // Check every 1 second
}

// Enhanced auto-start llama.cpp server with better polling
async function autoStartLlamaCppServer() {
    try {
        const response = await fetch('/api/settings');
        const data = await response.json();
        
        if (data.success && data.settings) {
            const settings = data.settings;
            
            // Check if provider is llama.cpp and auto_start is enabled
            if (settings.provider === 'llamacpp' && settings.llamacpp?.auto_start && settings.llamacpp?.model) {
                console.log('[LLAMA.CPP] Auto-start enabled, checking server status...');
                
                // Check if server is already running
                const statusResponse = await fetch('/api/llamacpp/server/status');
                const statusData = await statusResponse.json();
                
                if (statusData.success && !statusData.running) {
                    console.log('[LLAMA.CPP] Server not running, starting with model:', settings.llamacpp.model);
                    
                    // Start the server
                    const startResponse = await fetch('/api/llamacpp/server/start', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({model: settings.llamacpp.model})
                    });
                    
                    const startData = await startResponse.json();
                    
                    if (startData.success) {
                        console.log('[LLAMA.CPP] Server started successfully, PID:', startData.pid);
                        
                        // Update status to show server is starting
                        if (statusDot) {
                            statusDot.className = 'status-dot connecting';
                            statusText.textContent = 'llama.cpp (starting...)';
                        }
                        
                        // Start enhanced polling for server readiness
                        console.log('[LLAMA.CPP] Starting enhanced polling for server readiness...');
                        pollLlamaCppServer();
                    } else {
                        console.error('[LLAMA.CPP] Failed to start server:', startData.error);
                    }
                } else if (statusData.running) {
                    console.log('[LLAMA.CPP] Server already running');
                }
            }
        }
    } catch (error) {
        console.error('[LLAMA.CPP] Error during auto-start check:', error);
    }
}

// ==================== LLAMA.CPP SERVER DOWNLOAD & CONTROL ====================

// llama.cpp server download elements
const downloadLlamaCppServerBtn = document.getElementById('downloadLlamaCppServerBtn');
const llamacppServerDownloadProgress = document.getElementById('llamacppServerDownloadProgress');
const llamacppServerDownloadFilename = document.getElementById('llamacppServerDownloadFilename');
const llamacppServerDownloadStatus = document.getElementById('llamacppServerDownloadStatus');
const llamacppServerDownloadProgressBar = document.getElementById('llamacppServerDownloadProgressBar');
const llamacppServerDownloadSpeed = document.getElementById('llamacppServerDownloadSpeed');
const llamacppServerDownloadEta = document.getElementById('llamacppServerDownloadEta');
const llamacppServerDownloadPercent = document.getElementById('llamacppServerDownloadPercent');
const llamacppServerStopDownloadBtn = document.getElementById('llamacppServerStopDownloadBtn');
const llamacppServerStatusDiv = document.getElementById('llamacppServerStatus');
const startLlamaCppServerBtn = document.getElementById('startLlamaCppServerBtn');
const stopLlamaCppServerBtn = document.getElementById('stopLlamaCppServerBtn');

let llamacppServerCurrentDownloadId = null;
let llamacppServerDownloadInterval = null;

// Check llama.cpp server status on load
async function checkLlamaCppServerStatus() {
    try {
        const response = await fetch('/api/llamacpp/server/status');
        const data = await response.json();
        
        if (data.success && llamacppServerStatusDiv) {
            if (data.binary_found) {
                llamacppServerStatusDiv.innerHTML = '<span style="color: #10b981;">✓ Server binary ready: ' + data.binary_name + '</span>';
            } else if (data.archive_files && data.archive_files.length > 0) {
                llamacppServerStatusDiv.innerHTML = '<span style="color: #f59e0b;">⚠ Found archive files that need extraction: ' + data.archive_files.join(', ') + '</span>';
            } else {
                llamacppServerStatusDiv.innerHTML = '<span style="color: #ef4444;">✗ Server binary not found. Download it below.</span>';
            }
        }
    } catch (error) {
        console.error('Error checking llama.cpp server status:', error);
    }
}

// Download llama.cpp server
if (downloadLlamaCppServerBtn) {
    downloadLlamaCppServerBtn.addEventListener('click', async () => {
        try {
            downloadLlamaCppServerBtn.disabled = true;
            downloadLlamaCppServerBtn.textContent = 'Starting download...';
            
            const response = await fetch('/api/llamacpp/server/download', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({release_id: 'windows-cpu'})
            });
            
            const data = await response.json();
            
            if (data.success) {
                llamacppServerCurrentDownloadId = data.download_id;
                llamacppServerDownloadProgress.style.display = 'block';
                llamacppServerDownloadFilename.textContent = data.filename;
                
                // Start polling for download status
                llamacppServerDownloadInterval = setInterval(async () => {
                    try {
                        const statusResponse = await fetch('/api/llamacpp/server/download/status?id=' + llamacppServerCurrentDownloadId);
                        const statusData = await statusResponse.json();
                        
                        if (statusData.success) {
                            const download = statusData.download;
                            llamacppServerDownloadStatus.textContent = download.status;
                            llamacppServerDownloadProgressBar.style.width = download.progress + '%';
                            llamacppServerDownloadPercent.textContent = download.progress.toFixed(1) + '%';
                            
                            // Handle different status types
                            if (download.status === 'installing') {
                                // For wheel installation, hide speed/eta
                                llamacppServerDownloadSpeed.textContent = '';
                                llamacppServerDownloadEta.textContent = '';
                            } else {
                                // For downloads, show speed/eta
                                llamacppServerDownloadSpeed.textContent = (download.speed / 1024 / 1024).toFixed(2) + ' MB/s';
                                
                                if (download.eta > 0) {
                                    const mins = Math.floor(download.eta / 60);
                                    const secs = Math.floor(download.eta % 60);
                                    llamacppServerDownloadEta.textContent = mins + ':' + secs.toString().padStart(2, '0');
                                }
                            }
                            
                            if (download.status === 'completed') {
                                clearInterval(llamacppServerDownloadInterval);
                                llamacppServerDownloadStatus.textContent = 'Installation complete!';
                                downloadLlamaCppServerBtn.disabled = false;
                                downloadLlamaCppServerBtn.textContent = 'Download llama.cpp Server';
                                checkLlamaCppServerStatus();
                            } else if (download.status === 'error') {
                                clearInterval(llamacppServerDownloadInterval);
                                llamacppServerDownloadStatus.textContent = 'Error: ' + download.error;
                                downloadLlamaCppServerBtn.disabled = false;
                                downloadLlamaCppServerBtn.textContent = 'Download llama.cpp Server';
                            } else if (download.status === 'cancelled') {
                                clearInterval(llamacppServerDownloadInterval);
                                llamacppServerDownloadStatus.textContent = 'Cancelled';
                                downloadLlamaCppServerBtn.disabled = false;
                                downloadLlamaCppServerBtn.textContent = 'Download llama.cpp Server';
                            }
                        }
                    } catch (error) {
                        console.error('Error checking download status:', error);
                    }
                }, 1000);
            } else {
                alert('Failed to start download: ' + (data.error || 'Unknown error'));
                downloadLlamaCppServerBtn.disabled = false;
                downloadLlamaCppServerBtn.textContent = 'Download llama.cpp Server';
            }
        } catch (error) {
            console.error('Error downloading llama.cpp server:', error);
            alert('Error: ' + error.message);
            downloadLlamaCppServerBtn.disabled = false;
            downloadLlamaCppServerBtn.textContent = 'Download llama.cpp Server';
        }
    });
}

// Stop llama.cpp server download
if (llamacppServerStopDownloadBtn) {
    llamacppServerStopDownloadBtn.addEventListener('click', async () => {
        try {
            await fetch('/api/llamacpp/server/download/stop', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({download_id: llamacppServerCurrentDownloadId})
            });
            
            if (llamacppServerDownloadInterval) {
                clearInterval(llamacppServerDownloadInterval);
            }
            
            llamacppServerDownloadProgress.style.display = 'none';
            downloadLlamaCppServerBtn.disabled = false;
            downloadLlamaCppServerBtn.textContent = 'Download llama.cpp Server';
        } catch (error) {
            console.error('Error stopping download:', error);
        }
    });
}

// Start llama.cpp server
if (startLlamaCppServerBtn) {
    startLlamaCppServerBtn.addEventListener('click', async () => {
        const model = modelSelect ? modelSelect.value : '';
        
        if (!model) {
            alert('Please select a model first');
            return;
        }
        
        try {
            startLlamaCppServerBtn.disabled = true;
            startLlamaCppServerBtn.textContent = 'Starting...';
            
            const response = await fetch('/api/llamacpp/server/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({model: model})
            });
            
            const data = await response.json();
            
            if (data.success) {
                alert('Server started successfully!\n\nCommand: ' + data.command + '\nPID: ' + data.pid);
            } else {
                alert('Failed to start server: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error starting server:', error);
            alert('Error: ' + error.message);
        } finally {
            startLlamaCppServerBtn.disabled = false;
            startLlamaCppServerBtn.textContent = 'Start Server';
        }
    });
}

// Stop llama.cpp server
if (stopLlamaCppServerBtn) {
    stopLlamaCppServerBtn.addEventListener('click', async () => {
        try {
            stopLlamaCppServerBtn.disabled = true;
            stopLlamaCppServerBtn.textContent = 'Stopping...';
            
            const response = await fetch('/api/llamacpp/server/stop', {
                method: 'POST'
            });
            
            const data = await response.json();
            
            if (data.success) {
                alert('Server stopped. Killed PIDs: ' + (data.killed_pids || []).join(', '));
            } else {
                alert('Failed to stop server: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error stopping server:', error);
            alert('Error: ' + error.message);
        } finally {
            stopLlamaCppServerBtn.disabled = false;
            stopLlamaCppServerBtn.textContent = 'Stop Server';
        }
    });
}

// Check server status when settings modal opens (if the function exists)
if (typeof openSettingsModal !== 'undefined') {
    const originalOpenSettings = openSettingsModal;
    window.openSettingsModal = async function() {
        await originalOpenSettings();
        checkLlamaCppServerStatus();
    };
}

// Also check on page load
checkLlamaCppServerStatus();

// Wrap loadSettings to load LLM models when provider is llama.cpp
const originalLoadSettingsFn = loadSettings;
window.loadSettings = async function() {
    await originalLoadSettingsFn();
    
    // Load LLM models for llama.cpp dropdown when provider is llama.cpp
    if (providerSelect && providerSelect.value === 'llamacpp') {
        loadLlmModelsForLlamaCpp();
    }
};

// Auto-start llama.cpp server if configured in settings
async function autoStartLlamaCppServer() {
    try {
        const response = await fetch('/api/settings');
        const data = await response.json();
        
        if (data.success && data.settings) {
            const settings = data.settings;
            
            // Check if provider is llama.cpp and auto_start is enabled
            if (settings.provider === 'llamacpp' && settings.llamacpp?.auto_start && settings.llamacpp?.model) {
                console.log('[LLAMA.CPP] Auto-start enabled, checking server status...');
                
                // Check if server is already running
                const statusResponse = await fetch('/api/llamacpp/server/status');
                const statusData = await statusResponse.json();
                
                if (statusData.success && !statusData.running) {
                    console.log('[LLAMA.CPP] Server not running, starting with model:', settings.llamacpp.model);
                    
                    // Start the server
                    const startResponse = await fetch('/api/llamacpp/server/start', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({model: settings.llamacpp.model})
                    });
                    
                    const startData = await startResponse.json();
                    
                    if (startData.success) {
                        console.log('[LLAMA.CPP] Server started successfully, PID:', startData.pid);
                        
                        // Wait for server to be ready (poll health endpoint)
                        console.log('[LLAMA.CPP] Waiting for server to be ready...');
                        const maxWaitTime = 30000; // 30 seconds max wait
                        const checkInterval = 1000; // Check every 1 second
                        let waited = 0;
                        
                        // Use XMLHttpRequest instead of fetch to avoid browser error logging for 503/404 responses
                        const serverUrl = settings.llamacpp.base_url || 'http://localhost:8080';
                        
                        while (waited < maxWaitTime) {
                            await new Promise(resolve => setTimeout(resolve, checkInterval));
                            waited += checkInterval;
                            
                            // Use synchronous-style check with XMLHttpRequest
                            const result = await new Promise((resolve) => {
                                const xhr = new XMLHttpRequest();
                                xhr.open('GET', serverUrl + '/v1/models', true);
                                xhr.timeout = 5000;
                                
                                xhr.onload = function() {
                                    resolve({ status: xhr.status, success: true });
                                };
                                
                                xhr.onerror = function() {
                                    resolve({ success: false, error: 'network' });
                                };
                                
                                xhr.ontimeout = function() {
                                    resolve({ success: false, error: 'timeout' });
                                };
                                
                                xhr.send();
                            });
                            
                            if (result.success) {
                                const status = result.status;
                                // Accept 200-299 as ready, treat 503/404 as "starting up, keep waiting"
                                if (status >= 200 && status < 300) {
                                    console.log('[LLAMA.CPP] Server is ready after', waited/1000, 'seconds');
                                    break;
                                } else if (status === 503 || status === 404) {
                                    // Server is running but still initializing or endpoint doesn't exist
                                    console.log('[LLAMA.CPP] Server responding (status ' + status + '), waiting for full initialization...');
                                } else {
                                    // Other status codes - keep waiting
                                    console.log('[LLAMA.CPP] Server responding (status ' + status + '), waiting...');
                                }
                            } else {
                                // Network error or timeout - server not ready yet
                                console.log('[LLAMA.CPP] Server not responding yet, waiting...');
                            }
                        }
                        
                        // Update status indicator
                        if (statusDot) {
                            statusDot.className = 'status-dot connected';
                            statusText.textContent = 'llama.cpp';
                        }
                    } else {
                        console.error('[LLAMA.CPP] Failed to start server:', startData.error);
                    }
                } else if (statusData.running) {
                    console.log('[LLAMA.CPP] Server already running');
                }
            }
        }
    } catch (error) {
        console.error('[LLAMA.CPP] Error during auto-start check:', error);
    }
}

// Note: loadLlmModelsForLlamaCpp is called explicitly when:
// - Settings button is clicked (if provider is llamacpp)
// - Provider is switched to llamacpp
// No need for automatic reload on modal transitions

// Save system prompt
async function saveSystemPromptHandler() {
    const systemPrompt = systemPromptInput ? systemPromptInput.value : '';
    const globalSystemPrompt = globalSystemPromptInput ? globalSystemPromptInput.value : '';
    
    try {
        const response = await fetch('/api/system-prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                system_prompt: systemPrompt,
                global_system_prompt: globalSystemPrompt
            })
        });
        
        const data = await response.json();
        
        if (!data.success) {
            console.error('Error saving system prompt:', data.error);
        }
    } catch (error) {
        console.error('Error saving system prompt:', error);
    }
}

// Load system prompt
async function loadSystemPrompt() {
    try {
        const response = await fetch('/api/system-prompt');
        const data = await response.json();
        
        if (data.success) {
            if (systemPromptInput && data.system_prompt) {
                systemPromptInput.value = data.system_prompt;
            }
            if (globalSystemPromptInput && data.global_system_prompt) {
                globalSystemPromptInput.value = data.global_system_prompt;
            }
        }
    } catch (error) {
        console.error('Error loading system prompt:', error);
    }
}

// Fallback create new session function for when SessionManager is not available
async function createNewSession() {
    try {
        const response = await fetch('/api/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();
        
        if (data.success) {
            sessionId = data.session_id;
            messagesContainer.innerHTML = '';
            welcomeMessage.classList.remove('hidden');
            // Try to reload sessions if SessionManager becomes available
            if (typeof SessionManager?.loadSessions === 'function') {
                SessionManager.loadSessions();
            }
        }
    } catch (error) {
        console.error('Error creating session:', error);
    }
}

