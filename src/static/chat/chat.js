/**
 * LM Studio Chatbot - Main Chat Module
 * Orchestrates all chat functionality
 */

// Wait for DOM ready
document.addEventListener('DOMContentLoaded', () => {
    console.log('[CHAT] Initializing chat module...');
    
    // Wait for all dependencies to load
    const initChat = () => {
        // Check that all modules are loaded
        if (!window.SessionManager || !window.MessageRenderer || 
            !window.AudioPlayer || !window.TTSQueue || !window.ChatAPI) {
            setTimeout(initChat, 100);
            return;
        }
        
        console.log('[CHAT] All modules loaded, initializing...');
        
        // Initialize session manager (loads sessions and sets up sessionId)
        SessionManager.loadSessions();
        
        // Setup event listeners for main controls
        setupChatControls();
        
        console.log('[CHAT] Chat module initialized');
    };
    
    // Add a longer timeout to ensure all modules have time to load
    setTimeout(initChat, 500);
});

// Setup chat control event listeners
function setupChatControls() {
    // Send button
    if (sendBtn) {
        sendBtn.addEventListener('click', () => {
            if (typeof ChatAPI.sendMessage === 'function') {
                ChatAPI.sendMessage();
            }
        });
    }
    
    // Message input
    if (messageInput) {
        messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (typeof ChatAPI.sendMessage === 'function') {
                    ChatAPI.sendMessage();
                }
            }
        });
        
        messageInput.addEventListener('input', () => {
            messageInput.style.height = 'auto';
            messageInput.style.height = Math.min(messageInput.scrollHeight, 150) + 'px';
            if (sendBtn) {
                sendBtn.disabled = !messageInput.value.trim() || isLoading;
            }
        });
    }
    
    // Clear button
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            if (typeof ChatAPI.clearChat === 'function') {
                ChatAPI.clearChat();
            }
        });
    }
    
    // Welcome speaker button
    const welcomeSpeakerBtn = document.getElementById('welcomeSpeakerBtn');
    if (welcomeSpeakerBtn) {
        welcomeSpeakerBtn.addEventListener('click', async () => {
            // Reset state
            welcomeSpeakerBtn.classList.remove('success', 'error', 'unavailable');

            const isTtsAvailable =
                document.getElementById('xttsStatusDot')?.classList.contains('connected') === true;
            const speakFn =
                window.ChatAPI?.speakText ||
                window.speakText ||
                window.ChatAPI?.speakTextStreaming ||
                window.speakTextStreaming;

            if (!isTtsAvailable || typeof speakFn !== 'function') {
                welcomeSpeakerBtn.classList.add('unavailable');
                setTimeout(() => {
                    welcomeSpeakerBtn.classList.remove('unavailable');
                }, 3000);
                return;
            }
            
            // Track success flag
            let ttsSucceeded = false;
            
            // Override console.error temporarily to catch TTS errors
            const originalConsoleError = console.error;
            const ttsErrors = [];
            
            console.error = function(...args) {
                originalConsoleError.apply(console, args);
                // Detect all TTS, FastAPI, and server errors
                if (args.some(arg => {
                    const strArg = String(arg);
                    return strArg.includes('[TTS]') ||
                           strArg.includes('api/tts') ||
                           strArg.includes('HTTP 500') ||
                           strArg.includes('Internal Server Error') ||
                           strArg.includes('Failed to load resource') ||
                           strArg.includes('NetworkError') ||
                           strArg.includes('tts_server') ||
                           strArg.includes('FastAPI');
                })) {
                    ttsErrors.push(args);
                }
            };
            
            try {
                await speakFn("Hello, welcome to Omnix chat");
                
                // Check if any TTS errors were logged
                ttsSucceeded = ttsErrors.length === 0;
                
            } catch (e) {
                ttsSucceeded = false;
            } finally {
                // Restore original console.error
                console.error = originalConsoleError;
                
                // Set status
                if (ttsSucceeded) {
                    welcomeSpeakerBtn.classList.add('success');
                } else {
                    welcomeSpeakerBtn.classList.add('error');
                }
                
                // Clear state after 3 seconds
                setTimeout(() => {
                    welcomeSpeakerBtn.classList.remove('success', 'error', 'unavailable');
                }, 3000);
            }
        });
    }
    
    // New chat button - use SessionManager
    const newChatBtns = [
        document.getElementById('newChatBtn'),
        document.getElementById('newChatBtnOption'),
        document.getElementById('newChatBtnCollapsed')
    ];
    
    newChatBtns.forEach(btn => {
        if (btn) {
            btn.addEventListener('click', () => {
                if (typeof SessionManager.createNewSession === 'function') {
                    SessionManager.createNewSession();
                }
            });
        }
    });
}

// Make globally available
window.ChatModule = {
    SessionManager: window.SessionManager,
    MessageRenderer: window.MessageRenderer,
    AudioPlayer: window.AudioPlayer,
    TTSQueue: window.TTSQueue,
    ChatAPI: window.ChatAPI
};

console.log('[CHAT] chat.js loaded');
