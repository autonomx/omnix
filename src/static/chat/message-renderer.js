/**
 * LM Studio Chatbot - Message Renderer
 * Handles message display and markdown rendering
 */

// Current audio element for playback - SEPARATE from voice.js currentAudio

// Add message to chat
function addMessage(role, content, thinking = null, tokens = null, tokensPerSec = '', attachments = null) {

    if (role === 'assistant') role = 'ai';

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    // Add attachments display
    if (attachments && attachments.length > 0) {
        console.log('[DEBUG] Rendering attachments:', attachments);
        const attachmentsDiv = document.createElement('div');
        attachmentsDiv.className = 'message-attachments';
        
        for (const att of attachments) {
            // Check if it's an image - handle both processed attachments and raw file objects
            const isImage = att.type === 'image' || 
                (att.type && att.type.startsWith('image/')) ||
                (att.name && att.name.match(/\.(png|jpe?g|gif|webp|bmp|svg)$/i));
            console.log('[DEBUG] Attachment:', att.name, 'isImage:', isImage, 'type:', att.type);
            
            if (isImage) {
                const img = document.createElement('img');
                // Handle both processed (att.data) and raw file objects (URL.createObjectURL)
                img.src = att.data || (att instanceof File ? URL.createObjectURL(att) : att.name);
                img.alt = att.name;
                img.className = 'message-attachment-image';
                console.log('[DEBUG] Created image element, src:', img.src.substring(0, 50));
                
                // Add click handler to open image modal
                img.style.cursor = 'pointer';
                img.addEventListener('click', () => {
                    const modal = document.getElementById('imageModal');
                    const modalImg = document.getElementById('imageModalImg');
                    modalImg.src = img.src;
                    modal.classList.add('active');
                });
                
                attachmentsDiv.appendChild(img);
            } else {
                const doc = document.createElement('div');
                doc.className = 'message-attachment-doc';
                doc.innerHTML = `<span class="doc-icon">📄</span> ${att.name}`;
                attachmentsDiv.appendChild(doc);
            }
        }
        
        messageDiv.appendChild(attachmentsDiv);
    }
    
    if (role === 'ai' || role === 'assistant') {
        if (thinking) {
            const thinkingContainer = document.createElement('div');
            thinkingContainer.className = 'thinking-container collapsed';
            
            const thinkingHeader = document.createElement('div');
            thinkingHeader.className = 'thinking-header';
            thinkingHeader.innerHTML = `
                <span class="thinking-toggle">▶ Thinking</span>
                <span class="thinking-label">(${thinking.length} chars)</span>
            `;
            
            const thinkingContent = document.createElement('div');
            thinkingContent.className = 'thinking-content';
            thinkingContent.textContent = thinking;
            
            thinkingHeader.addEventListener('click', () => {
                thinkingContainer.classList.toggle('collapsed');
                thinkingHeader.querySelector('.thinking-toggle').textContent = 
                    thinkingContainer.classList.contains('collapsed') ? '▶ Thinking' : '▼ Thinking';
            });
            
            thinkingContainer.appendChild(thinkingHeader);
            thinkingContainer.appendChild(thinkingContent);
            messageDiv.appendChild(thinkingContainer);
        }
        
        let headerHTML = `<span class="message-label">AI</span>`;
        if (tokens) {
            headerHTML += `<span class="token-info">${tokens.completion || 0} tokens`;
            if (tokensPerSec) {
                headerHTML += ` • ${tokensPerSec} tok/s`;
            }
            headerHTML += '</span>';
        }
        headerHTML += `<button class="speak-btn" title="Speak">Speak</button>`;
        headerHTML += `<button class="pause-btn" title="Pause" style="display: none;">⏸</button>`;
        headerHTML += `<button class="stop-btn" title="Stop" style="display: none;">⏹</button>`;
        headerHTML += `<button class="copy-btn" title="Copy">Copy</button>`;
        
        const headerDiv = document.createElement('div');
        headerDiv.className = 'message-header';
        headerDiv.innerHTML = headerHTML;
        
        headerDiv.querySelector('.copy-btn').addEventListener('click', (e) => {
            copyToClipboard(content, e.target);
        });
        
        headerDiv.querySelector('.stop-btn').addEventListener('click', () => {
            console.log('[STOP] Stop button clicked');
            
            fetch('/api/tts/stream/cancel', { method: 'POST' }).catch(() => {});
            
            if (typeof window.stopTTSAudio === 'function') {
                window.stopTTSAudio();
            }
            
            setTTSButtonState(messageDiv, 'idle');
        });
        
        // Remove duplicate handler
        headerDiv.querySelector('.stop-btn').onclick = null;
        
        headerDiv.querySelector('.speak-btn').addEventListener('click', () => {
            console.log('[TTS] Speak button clicked');
            currentMessageDiv = messageDiv;
            
            // If paused, resume playback instead of restarting TTS
            if (window.isPaused) {
                window.isPaused = false;

                ensureAudioContext();
                playQueuedAudio();

                setTTSButtonState(messageDiv, 'playing');
                return;
            }
            
            setTTSButtonState(messageDiv, 'playing');
            
            const ttsSpeakerSelect = document.getElementById('ttsSpeaker');
            speakText(content, ttsSpeakerSelect ? ttsSpeakerSelect.value : 'en').then(() => {
                console.log('[TTS] Speak completed');
                setTTSButtonState(messageDiv, 'idle');
            }).catch((err) => {
                console.error('[TTS] Speak error:', err);
                setTTSButtonState(messageDiv, 'idle');
            });
        });
        
        messageDiv.appendChild(headerDiv);
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.innerHTML = renderMarkdown(content);
        messageDiv.appendChild(contentDiv);
    } else {
        const textContent = document.createElement('span');
        textContent.textContent = content;
        messageDiv.appendChild(textContent);
    }
    
    messagesContainer.appendChild(messageDiv);
    scrollToBottom();
}

// Extract thinking from streamed content
function extractThinkingFromContent(content) {
    if (!content) return { thinking: '', content: '' };
    
    const lines = content.split('\n');
    let thinkingLines = [];
    let answerLines = [];
    let foundThinkingMarker = false;
    
    for (let i = 0; i < lines.length; i++) {
        const stripped = lines[i].trim();
        
        if (stripped && /^\d+\.\s/.test(stripped)) {
            if (!foundThinkingMarker && i > 0) {
                const prevLines = lines.slice(0, i).join('\n');
                const markers = ['analyze', 'identify', 'determine', 'formulate', 'check', 'output'];
                if (markers.some(m => prevLines.toLowerCase().includes(m))) {
                    thinkingLines = lines.slice(0, i);
                    answerLines = lines.slice(i);
                    foundThinkingMarker = true;
                    continue;
                }
            }
        }
        
        if (!foundThinkingMarker) {
            const markers = ['analyze', 'identify the intent', 'determine the answer', 'formulate', 'final output'];
            if (markers.some(m => stripped.toLowerCase().includes(m))) {
                thinkingLines = lines.slice(0, i);
                answerLines = lines.slice(i);
                foundThinkingMarker = true;
            }
        }
    }
    
    if (thinkingLines.length > 0 && answerLines.length > 0) {
        const thinkingText = thinkingLines.join('\n').trim();
        const answerText = answerLines.join('\n').trim();
        
        const markers = ['analyze', 'identify', 'determine', 'formulate', 'check', 'output'];
        if (thinkingText.length > 20 && markers.some(m => thinkingText.toLowerCase().includes(m))) {
            return { thinking: thinkingText, content: answerText };
        }
    }
    
    if (content.toLowerCase().includes('</thinking>')) {
        const parts = content.split(/<\/thinking>/i);
        if (parts.length > 1) {
            return { thinking: parts[0].trim(), content: parts[1].trim() };
        }
    }
    
    return { thinking: '', content: content };
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

// Export for use in other modules
window.MessageRenderer = {
    addMessage,
    extractThinkingFromContent,
    renderMarkdown,
    copyToClipboard,
    scrollToBottom
};

// Initialize image modal close handlers
(function initImageModal() {
    const modal = document.getElementById('imageModal');
    const closeBtn = document.querySelector('.image-modal-close');
    
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            modal.classList.remove('active');
        });
    }
    
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.remove('active');
            }
        });
        
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && modal.classList.contains('active')) {
                modal.classList.remove('active');
            }
        });
    }
})();