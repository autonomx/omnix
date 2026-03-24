/**
 * LM Studio Chatbot - Session Manager
 * Handles session CRUD operations
 */

// Make functions globally accessible
window.loadSessions = loadSessions;
window.renderSessionList = renderSessionList;
window.createNewSession = createNewSession;
window.switchSession = switchSession;
window.loadSession = loadSession;
window.deleteSession = deleteSession;
window.renderHistory = renderHistory;
window.updateSessionTitle = updateSessionTitle;

// Delete history item from history modal
function deleteHistoryItem(id) {
    if (confirm('Delete this chat?')) {
        deleteSession(id);
        document.getElementById('hist-' + id)?.remove();
    }
}
window.deleteHistoryItem = deleteHistoryItem;

// Generate title from first user message
function generateSessionTitle(userMessage) {
    if (!userMessage) return 'New Chat';
    
    // Get first line or first 50 chars
    const firstLine = userMessage.split('\n')[0].trim();
    const title = firstLine.length > 50 ? firstLine.substring(0, 47) + '...' : firstLine;
    
    return title || 'New Chat';
}

// Update session title
async function updateSessionTitle(sessionId, title) {
    try {
        await fetch(`/api/sessions/${sessionId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title })
        });
    } catch (error) {
        console.error('Error updating session title:', error);
    }
}

// Load sessions
async function loadSessions() {
    try {
        const response = await fetch('/api/sessions');
        const data = await response.json();
        
        if (data.success) {
            window.sessions = data.sessions || [];
            renderSessionList();
            
            if (window.sessions.length > 0) {
                window.sessionId = window.sessions[0].id;
                await loadSession(window.sessionId);
            } else {
                await createNewSession();
            }
        }
    } catch (error) {
        console.error('Error loading sessions:', error);
        await createNewSession();
    }
}

// Render session list
function renderSessionList() {
    sessionList.innerHTML = '';
    
    // Also render collapsed session list
    const collapsedSessionList = document.getElementById('sidebarCollapsedSessionList');
    if (collapsedSessionList) {
        collapsedSessionList.innerHTML = '';
    }
    
    window.sessions.forEach(s => {
        const item = document.createElement('div');
        item.className = `session-item ${s.id === window.sessionId ? 'active' : ''}`;
        item.innerHTML = `
            <span class="session-title">${s.title || 'New Chat'}</span>
            <button class="session-delete" title="Delete">×</button>
        `;
        
        item.addEventListener('click', (e) => {
            if (!e.target.classList.contains('session-delete')) {
                switchSession(s.id);
            }
        });
        
        item.querySelector('.session-delete').addEventListener('click', (e) => {
            e.stopPropagation();
            deleteSession(s.id);
        });
        
        sessionList.appendChild(item);
        
        // Render collapsed session item (icon with tooltip)
        if (collapsedSessionList) {
            const collapsedItem = document.createElement('button');
            collapsedItem.className = `sidebar-collapsed-session-item ${s.id === window.sessionId ? 'active' : ''}`;
            collapsedItem.innerHTML = `
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                    <path d="M21 15C21 15.5304 20.7893 16.0391 20.4142 16.4142C20.0391 16.7893 19.5304 17 19 17H7L3 21V5C3 4.46957 3.21071 3.96086 3.58579 3.58579C3.96086 3.21071 4.46957 3 5 3H19C19.5304 3 20.0391 3.21071 20.4142 3.58579C20.7893 3.96086 21 4.46957 21 5V15Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                <span class="session-tooltip">${s.title || 'New Chat'}</span>
            `;
            
            // Position tooltip on hover
            collapsedItem.addEventListener('mouseenter', (e) => {
                const tooltip = collapsedItem.querySelector('.session-tooltip');
                if (tooltip) {
                    const rect = collapsedItem.getBoundingClientRect();
                    tooltip.style.left = rect.right + 8 + 'px';
                    tooltip.style.top = rect.top + (rect.height / 2) + 'px';
                    tooltip.style.transform = 'translateY(-50%)';
                }
            });
            
            collapsedItem.addEventListener('click', () => {
                switchSession(s.id);
            });
            
            collapsedSessionList.appendChild(collapsedItem);
        }
    });
}

// Render history dialog
function renderHistory() {
    const historyList = document.getElementById('historyList');
    if (!historyList) return;
    
    historyList.innerHTML = '';
    
    if (window.sessions.length === 0) {
        historyList.innerHTML = '<p style="text-align: center; color: var(--text-muted);">No chat history</p>';
        return;
    }
    
    // Sort sessions by updated_at (newest first)
    const sortedSessions = [...window.sessions].sort((a, b) => {
        const dateA = new Date(a.updated_at || 0);
        const dateB = new Date(b.updated_at || 0);
        return dateB - dateA;
    });
    
    sortedSessions.forEach(s => {
        const item = document.createElement('div');
        item.className = `history-item ${s.id === window.sessionId ? 'active' : ''}`;
        
        const date = s.updated_at ? new Date(s.updated_at).toLocaleDateString() : '';
        
        item.innerHTML = `
            <span class="history-item-title">${s.title || 'New Chat'}</span>
            <span class="history-item-date">${date}</span>
            <button class="history-item-delete" title="Delete">×</button>
        `;
        
        item.addEventListener('click', (e) => {
            if (!e.target.classList.contains('history-item-delete')) {
                switchSession(s.id);
                closeHistoryModal();
            }
        });
        
        item.querySelector('.history-item-delete').addEventListener('click', (e) => {
            e.stopPropagation();
            if (confirm('Delete this chat?')) {
                deleteSession(s.id);
            }
        });
        
        historyList.appendChild(item);
    });
}

// Open history modal
function openHistoryModal() {
    const modal = document.getElementById('historyModal');
    if (modal) {
        renderHistory();
        modal.style.display = 'flex';
    }
}

// Close history modal
function closeHistoryModal() {
    const modal = document.getElementById('historyModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

// Make functions globally accessible for onclick handlers
window.openHistoryModal = openHistoryModal;
window.closeHistoryModal = closeHistoryModal;

// Setup history modal events
function setupHistoryModal() {
    const historyBtn = document.getElementById('historyBtnOption');
    const historyBtnCollapsed = document.getElementById('historyBtnCollapsed');
    const closeBtn = document.getElementById('closeHistory');
    const modal = document.getElementById('historyModal');
    
    if (historyBtn) {
        historyBtn.addEventListener('click', openHistoryModal);
    }
    
    if (historyBtnCollapsed) {
        historyBtnCollapsed.addEventListener('click', openHistoryModal);
    }
    
    if (closeBtn) {
        closeBtn.addEventListener('click', closeHistoryModal);
    }
    
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeHistoryModal();
            }
        });
    }
}

// Create new session
async function createNewSession() {
    try {
        const response = await fetch('/api/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();
        
        if (data.success) {
            window.sessionId = data.session_id;
            messagesContainer.innerHTML = '';
            welcomeMessage.classList.remove('hidden');
            await loadSessions();
        }
    } catch (error) {
        console.error('Error creating session:', error);
    }
}

// Switch session
async function switchSession(id) {
    window.sessionId = id;
    await loadSession(id);
    renderSessionList();
}

// Load session
async function loadSession(id) {
    try {
        const response = await fetch(`/api/sessions/${id}`);
        const data = await response.json();
        
        if (data.success) {
            messagesContainer.innerHTML = '';
            
            const session = data.session;
            const messages = session.messages || [];
            
            if (messages.length === 0) {
                welcomeMessage.classList.remove('hidden');
            } else {
                welcomeMessage.classList.add('hidden');
                
                messages.forEach(msg => {
                    if (msg.role !== 'system') {
                        addMessage(msg.role, msg.content, msg.thinking || null);
                    }
                });
                
                // Ensure input area is visible when session has messages
                const inputArea = document.querySelector('.input-area');
                if (inputArea) {
                    inputArea.style.display = '';
                }
                
                // Focus on message input for immediate typing
                if (messageInput) {
                    messageInput.focus();
                }
            }
            
            if (session.system_prompt) {
                systemPromptInput.value = session.system_prompt;
            }
        }
    } catch (error) {
        console.error('Error loading session:', error);
    }
}

// Delete session
async function deleteSession(id) {
    try {
        await fetch(`/api/sessions/${id}`, { method: 'DELETE' });
        await loadSessions();
        renderHistory();
    } catch (error) {
        console.error('Error deleting session:', error);
    }
}

// Export for use in other modules
window.SessionManager = {
    loadSessions,
    createNewSession,
    switchSession,
    loadSession,
    deleteSession,
    renderSessionList,
    renderHistory,
    openHistoryModal,
    closeHistoryModal,
    generateSessionTitle,
    updateSessionTitle,
    get sessionId() { return window.sessionId; },
    set sessionId(val) { window.sessionId = val; },
    get sessions() { return window.sessions || []; },
    set sessions(val) { window.sessions = val; }
};

// Initialize history modal on DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupHistoryModal);
} else {
    setupHistoryModal();
}
