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
        welcomeSpeakerBtn.addEventListener('click', () => {
            if (typeof window.speakText === 'function') {
                window.speakText("Hello, welcome to Omnix chat");
            } else if (typeof window.speakTextStreaming === 'function') {
                window.speakTextStreaming("Hello, welcome to Omnix chat");
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