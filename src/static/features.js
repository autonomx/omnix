/**
 * LM Studio Chatbot - Features Module
 * Additional features: Theme, Search, Presets, Token Counter, etc.
 */

console.log('[FEATURES] features.js loaded');

// ============================================================
// THEME TOGGLE
// ============================================================

const themeToggle = document.getElementById('themeToggle');
const THEME_KEY = 'chatbot-theme';

// Initialize theme
function initTheme() {
    const savedTheme = localStorage.getItem(THEME_KEY) || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem(THEME_KEY, newTheme);
    updateThemeIcon(newTheme);
}

function updateThemeIcon(theme) {
    if (!themeToggle) return;
    const icon = themeToggle.querySelector('svg');
    if (theme === 'dark') {
        // Moon icon for dark mode (clicking switches to light)
        icon.innerHTML = `<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>`;
    } else {
        // Sun icon for light mode (clicking switches to dark)
        icon.innerHTML = `<circle cx="12" cy="12" r="5" stroke="currentColor" stroke-width="2"/><path d="M12 1V3M12 21V23M4.22 4.22L5.64 5.64M18.36 18.36L19.78 19.78M1 12H3M21 12H23M4.22 19.78L5.64 18.36M18.36 5.64L19.78 4.22" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>`;
    }
}

if (themeToggle) {
    themeToggle.addEventListener('click', toggleTheme);
}

// Initialize on load
initTheme();

// ============================================================
// SEARCH CONVERSATIONS
// ============================================================

const searchInput = document.getElementById('searchConversations');

function searchSessions(query) {
    if (!query) {
        renderSessionList();
        return;
    }
    
    const queryLower = query.toLowerCase();
    const filteredSessions = [];
    
    // Load sessions and filter
    if (typeof sessions_data !== 'undefined') {
        for (const [sid, data] of Object.entries(sessions_data)) {
            const titleMatch = data.title?.toLowerCase().includes(queryLower);
            const messageMatch = data.messages?.some(m => 
                m.content?.toLowerCase().includes(queryLower)
            );
            
            if (titleMatch || messageMatch) {
                filteredSessions.push({
                    id: sid,
                    title: data.title || 'New Chat',
                    updated_at: data.updated_at || '',
                    match: titleMatch ? 'title' : 'content'
                });
            }
        }
    }
    
    // Render filtered list
    if (typeof sessionList !== 'undefined') {
        sessionList.innerHTML = filteredSessions.map(session => `
            <div class="session-item ${sessionId === session.id ? 'active' : ''}" data-session-id="${session.id}">
                <div class="session-title">${escapeHtml(session.title)}</div>
                <div class="session-time">${formatSessionTime(session.updated_at)}</div>
                ${session.match === 'content' ? '<span class="search-match-badge">Content match</span>' : ''}
            </div>
        `).join('');
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatSessionTime(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
}

if (searchInput) {
    searchInput.addEventListener('input', (e) => {
        searchSessions(e.target.value.trim());
    });
}

// ============================================================
// SYSTEM PROMPT PRESETS
// ============================================================

const SYSTEM_PROMPT_PRESETS = {
    'conversational': {
        name: 'Conversational',
        prompt: `Personality:
You are a warm, empathetic, and human-like conversational AI. Your goal is to respond clearly, naturally, and helpfully, while remaining friendly and emotionally aware.

Style & Tone:

Respond in a concise, clear, and structured manner.

Maintain empathy and emotional awareness, but avoid over-explaining or rambling.

Use occasional light humor only if it does not distract from clarity.

Avoid long metaphors or unrelated examples.

Conversational Principles:

Listen and respond to user intent first.

Match emotional tone, but keep answers focused and coherent.

If uncertain, admit it briefly and suggest next steps.

Treat each turn as a real dialogue; do not write paragraphs for no reason.

Instructions for the LLM:

Limit responses to 2–5 sentences unless explicitly asked for more detail.

Avoid repetitive explanations or filler language.

Prioritize clarity, relevance, and emotional awareness over style flourish.`
    },
    'default': {
        name: 'Default Assistant',
        prompt: 'You are a helpful AI assistant.'
    },
    'coder': {
        name: 'Expert Coder',
        prompt: 'You are an expert software developer. Provide clear, well-structured code with explanations. Follow best practices, include error handling, and optimize for readability. Use appropriate design patterns and explain your architectural decisions.'
    },
    'writer': {
        name: 'Creative Writer',
        prompt: 'You are a skilled creative writer. Help with storytelling, character development, dialogue, and narrative structure. Be imaginative while respecting the user\'s creative vision. Offer constructive feedback on style, pacing, and engagement.'
    },
    'tutor': {
        name: 'Patient Tutor',
        prompt: 'You are a patient, encouraging tutor. Explain concepts step-by-step, use analogies and examples, check for understanding, and adapt to the learner\'s level. Celebrate progress and provide constructive feedback.'
    },
    'analyst': {
        name: 'Data Analyst',
        prompt: 'You are a data analyst expert. Help with data interpretation, statistical analysis, visualization recommendations, and drawing meaningful insights. Ask clarifying questions about data context and goals.'
    },
    'translator': {
        name: 'Translator',
        prompt: 'You are a professional translator. Provide accurate translations while preserving tone, context, and cultural nuances. Explain idioms and cultural references when helpful. Ask about preferred style (formal/casual).'
    },
    'debater': {
        name: 'Devil\'s Advocate',
        prompt: 'You are a skilled debater who can argue any side of an issue. Present balanced viewpoints, challenge assumptions respectfully, and help users think critically. Acknowledge valid points on all sides.'
    },
    'concise': {
        name: 'Concise Responder',
        prompt: 'You are a concise assistant. Provide brief, direct answers without unnecessary elaboration. Get straight to the point while remaining helpful and accurate. Use bullet points when appropriate.'
    }
};

const presetSelect = document.getElementById('systemPromptPreset');

function populatePresetDropdown() {
    if (!presetSelect) return;
    
    presetSelect.innerHTML = '<option value="">-- Select Preset --</option>';
    for (const [key, preset] of Object.entries(SYSTEM_PROMPT_PRESETS)) {
        const option = document.createElement('option');
        option.value = key;
        option.textContent = preset.name;
        presetSelect.appendChild(option);
    }
}

function applyPreset(presetKey) {
    if (!presetKey || !SYSTEM_PROMPT_PRESETS[presetKey]) return;
    
    const preset = SYSTEM_PROMPT_PRESETS[presetKey];
    const globalPromptInput = document.getElementById('globalSystemPrompt');
    
    if (systemPromptInput) {
        systemPromptInput.value = preset.prompt;
    }
    
    // Also update global prompt if desired
    if (globalPromptInput && confirm('Apply this preset as the global default for new chats?')) {
        globalPromptInput.value = preset.prompt;
    }
}

if (presetSelect) {
    presetSelect.addEventListener('change', (e) => {
        applyPreset(e.target.value);
    });
}

// ============================================================
// TOKEN COUNTER
// ============================================================

let totalPromptTokens = 0;
let totalCompletionTokens = 0;
let generationStartTime = null;
let tokenRateInterval = null;

// Get elements immediately - script is loaded after HTML
const tokenCounterEl = document.getElementById('tokenCounter');
const tokenRateEl = document.getElementById('tokenRate');

// Render initial display
renderTokenDisplay();

console.log('[TOKEN] Counter initialized:', { tokenCounterEl: !!tokenCounterEl, tokenRateEl: !!tokenRateEl });

function updateTokenCounter(prompt, completion, tokensPerSecond = null) {
    totalPromptTokens += prompt || 0;
    totalCompletionTokens += completion || 0;
    
    renderTokenDisplay(tokensPerSecond);
}

function renderTokenDisplay(tokensPerSecond = null) {
    if (tokenCounterEl) {
        tokenCounterEl.innerHTML = `
            <span class="token-stat" title="Input tokens">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
                    <path d="M12 2L2 7L12 12L22 7L12 2Z" stroke="currentColor" stroke-width="2"/>
                    <path d="M2 12L12 17L22 12" stroke="currentColor" stroke-width="2"/>
                </svg>
                ${totalPromptTokens.toLocaleString()}
            </span>
            <span class="token-stat" title="Output tokens">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
                    <path d="M22 2L11 13M22 2L15 22L11 13L2 9L22 2Z" stroke="currentColor" stroke-width="2"/>
                </svg>
                ${totalCompletionTokens.toLocaleString()}
            </span>
            <span class="token-stat total" title="Total tokens">
                ${(totalPromptTokens + totalCompletionTokens).toLocaleString()} total
            </span>
        `;
    }
    
    if (tokensPerSecond !== null && tokenRateEl) {
        tokenRateEl.textContent = `${tokensPerSecond.toFixed(1)} tok/s`;
        tokenRateEl.style.display = 'inline';
    }
}

// Estimate tokens from text (approx 4 chars per token for English)
function estimateTokens(text) {
    if (!text) return 0;
    return Math.ceil(text.length / 4);
}

// Update token counter from text content
function updateTokenCounterFromText(userText, aiText, generationTimeMs = null) {
    console.log('[TOKEN] updateTokenCounterFromText called:', { 
        userText: userText?.substring(0, 50), 
        aiText: aiText?.substring(0, 50), 
        generationTimeMs 
    });
    
    const promptTokens = estimateTokens(userText);
    const completionTokens = estimateTokens(aiText);
    
    console.log('[TOKEN] Estimated tokens:', { promptTokens, completionTokens });
    
    totalPromptTokens += promptTokens;
    totalCompletionTokens += completionTokens;
    
    let tokensPerSecond = null;
    if (generationTimeMs && completionTokens > 0) {
        tokensPerSecond = (completionTokens / generationTimeMs) * 1000;
    }
    
    console.log('[TOKEN] Totals:', { totalPromptTokens, totalCompletionTokens, tokensPerSecond });
    
    renderTokenDisplay(tokensPerSecond);
}

function startTokenRateTracking() {
    generationStartTime = performance.now();
}

function stopTokenRateTracking(completionTokens) {
    if (!generationStartTime || !completionTokens) return null;
    
    const elapsedSeconds = (performance.now() - generationStartTime) / 1000;
    const tokensPerSecond = completionTokens / elapsedSeconds;
    
    generationStartTime = null;
    return tokensPerSecond;
}

function resetSessionTokens() {
    totalPromptTokens = 0;
    totalCompletionTokens = 0;
    updateTokenCounter(0, 0);
    if (tokenRateEl) {
        tokenRateEl.style.display = 'none';
    }
}

// ============================================================
// TIMING METRICS - logs to console
// ============================================================

window.updateTimingSummary = function(metrics) {
    const ttft = metrics.llm > 0 ? metrics.llm.toFixed(0) : '--';
    const ttfa = metrics.tts > 0 ? metrics.tts.toFixed(0) : '--';
    const total = metrics.total > 0 ? metrics.total.toFixed(0) : '--';
    const tokens = metrics.tokens > 0 ? metrics.tokens : '--';
    const speed = metrics.tokensPerSecond > 0 ? metrics.tokensPerSecond.toFixed(1) : '--';
    
    console.log(`=== TIMING METRICS === Total: ${total}ms | TTFT: ${ttft}ms | TTFA: ${ttfa}ms | Tokens: ${tokens} | Speed: ${speed}/s`);
};

// ============================================================
// STREAMING CANCELLATION
// ============================================================

const stopGenerationBtn = document.getElementById('stopGenerationBtn');
let currentStreamReader = null;
let isStreaming = false;

function setStreamReader(reader) {
    currentStreamReader = reader;
    isStreaming = !!reader;
    
    if (stopGenerationBtn) {
        stopGenerationBtn.style.display = isStreaming ? 'flex' : 'none';
    }
    
    // Disable send button during streaming
    if (typeof sendBtn !== 'undefined') {
        sendBtn.disabled = isStreaming;
    }
}

async function cancelStreaming() {
    if (currentStreamReader) {
        try {
            await currentStreamReader.cancel();
            console.log('Stream cancelled by user');
        } catch (e) {
            console.error('Error cancelling stream:', e);
        }
        currentStreamReader = null;
    }
    
    isStreaming = false;
    isLoading = false;
    
    if (stopGenerationBtn) {
        stopGenerationBtn.style.display = 'none';
    }
    
    if (typeof typingIndicator !== 'undefined') {
        typingIndicator.style.display = 'none';
    }
    
    if (typeof sendBtn !== 'undefined' && typeof messageInput !== 'undefined') {
        sendBtn.disabled = !messageInput.value.trim();
    }
    
    if (typeof statusText !== 'undefined') {
        statusText.textContent = 'Cancelled';
        setTimeout(() => {
            if (typeof checkHealth === 'function') {
                checkHealth();
            }
        }, 1500);
    }
}

if (stopGenerationBtn) {
    stopGenerationBtn.addEventListener('click', cancelStreaming);
}

// ============================================================
// CODE BLOCK COPY BUTTON
// ============================================================

function addCopyButtonsToCodeBlocks() {
    // Find all code blocks
    document.querySelectorAll('pre code').forEach((codeBlock) => {
        // Skip if already has copy button
        if (codeBlock.parentElement.querySelector('.code-copy-btn')) return;
        
        const pre = codeBlock.parentElement;
        pre.style.position = 'relative';
        
        const copyBtn = document.createElement('button');
        copyBtn.className = 'code-copy-btn';
        copyBtn.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                <rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2"/>
                <path d="M5 15H4C2.89543 15 2 14.1046 2 13V4C2 2.89543 2.89543 2 4 2H13C14.1046 2 15 2.89543 15 4V5" stroke="currentColor" stroke-width="2"/>
            </svg>
            <span>Copy</span>
        `;
        
        copyBtn.addEventListener('click', async () => {
            const code = codeBlock.textContent;
            try {
                await navigator.clipboard.writeText(code);
                copyBtn.innerHTML = `
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                        <path d="M20 6L9 17L4 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                    <span>Copied!</span>
                `;
                copyBtn.classList.add('copied');
                
                setTimeout(() => {
                    copyBtn.innerHTML = `
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                            <rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2"/>
                            <path d="M5 15H4C2.89543 15 2 14.1046 2 13V4C2 2.89543 2.89543 2 4 2H13C14.1046 2 15 2.89543 15 4V5" stroke="currentColor" stroke-width="2"/>
                        </svg>
                        <span>Copy</span>
                    `;
                    copyBtn.classList.remove('copied');
                }, 2000);
            } catch (e) {
                console.error('Failed to copy:', e);
            }
        });
        
        pre.appendChild(copyBtn);
    });
}

// Override renderMarkdown to add copy buttons
const originalRenderMarkdown = typeof renderMarkdown !== 'undefined' ? renderMarkdown : null;
if (originalRenderMarkdown) {
    window.renderMarkdown = function(text) {
        const result = originalRenderMarkdown(text);
        // Add copy buttons after a small delay to allow DOM to update
        setTimeout(addCopyButtonsToCodeBlocks, 10);
        return result;
    };
}

// Observe DOM for new code blocks
const codeBlockObserver = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
        if (mutation.addedNodes.length) {
            addCopyButtonsToCodeBlocks();
        }
    });
});

// Start observing when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        codeBlockObserver.observe(document.body, { childList: true, subtree: true });
    });
} else {
    codeBlockObserver.observe(document.body, { childList: true, subtree: true });
}

// ============================================================
// VAD SENSITIVITY SLIDER
// ============================================================

const vadSlider = document.getElementById('vadSensitivity');
const vadValueDisplay = document.getElementById('vadSensitivityValue');
const VAD_SENSITIVITY_KEY = 'chatbot-vad-sensitivity';

function initVADSensitivity() {
    const saved = localStorage.getItem(VAD_SENSITIVITY_KEY);
    if (saved && vadSlider) {
        vadSlider.value = saved;
        updateVADSensitivity(saved);
    }
}

function updateVADSensitivity(value) {
    // Map slider value (1-10) to threshold (0.002 - 0.02)
    // Lower threshold = more sensitive
    const threshold = 0.002 + (10 - value) * 0.002;
    
    if (typeof VAD_SILENCE_THRESHOLD !== 'undefined') {
        window.VAD_SILENCE_THRESHOLD = threshold;
    }
    
    if (vadValueDisplay) {
        if (value <= 3) {
            vadValueDisplay.textContent = 'High sensitivity';
        } else if (value <= 6) {
            vadValueDisplay.textContent = 'Medium sensitivity';
        } else {
            vadValueDisplay.textContent = 'Low sensitivity';
        }
    }
    
    localStorage.setItem(VAD_SENSITIVITY_KEY, value);
    console.log(`VAD sensitivity set to ${value} (threshold: ${threshold})`);
}

if (vadSlider) {
    vadSlider.addEventListener('input', (e) => {
        updateVADSensitivity(e.target.value);
    });
    
    initVADSensitivity();
}

// ============================================================
// VOICE PROFILES (Per-voice personality prompts)
// ============================================================

const voiceProfilesKey = 'chatbot-voice-profiles';

// Default voice profiles for new installations
const DEFAULT_VOICE_PROFILES = {
    'Maya': {
        name: 'Maya',
        personality: `You are Maya, a warm, friendly voice. Keep responses short (1-3 sentences), be conversational, and match the user's tone. Use light humor when appropriate. Prioritize clarity and forward momentum.`,
        isDefault: true
    }
};

function getVoiceProfiles() {
    const saved = localStorage.getItem(voiceProfilesKey);
    if (saved) {
        const profiles = JSON.parse(saved);
        // Ensure Maya's default profile exists and has the default personality
        if (DEFAULT_VOICE_PROFILES['Maya']) {
            if (!profiles['Maya']) {
                // Maya doesn't exist - add the full default profile
                profiles['Maya'] = { ...DEFAULT_VOICE_PROFILES['Maya'] };
            } else if (!profiles['Maya'].personality || profiles['Maya'].personality.trim() === '') {
                // Maya exists but has no personality - add the default personality
                profiles['Maya'].personality = DEFAULT_VOICE_PROFILES['Maya'].personality;
                profiles['Maya'].isDefault = true;
            }
            // Save the merged/updated profiles
            localStorage.setItem(voiceProfilesKey, JSON.stringify(profiles));
        }
        return profiles;
    }
    // First time - return defaults and save them
    localStorage.setItem(voiceProfilesKey, JSON.stringify(DEFAULT_VOICE_PROFILES));
    return DEFAULT_VOICE_PROFILES;
}

function saveVoiceProfile(voiceId, profile) {
    const profiles = getVoiceProfiles();
    profiles[voiceId] = {
        ...profile,
        updatedAt: new Date().toISOString()
    };
    localStorage.setItem(voiceProfilesKey, JSON.stringify(profiles));
    renderVoicePersonalitiesList();
}

function getVoiceProfile(voiceId) {
    const profiles = getVoiceProfiles();
    return profiles[voiceId] || null;
}

function deleteVoiceProfile(voiceId) {
    const profiles = getVoiceProfiles();
    delete profiles[voiceId];
    localStorage.setItem(voiceProfilesKey, JSON.stringify(profiles));
    renderVoicePersonalitiesList();
}

// Get combined system prompt (global + voice personality)
function getCombinedSystemPrompt(voiceId) {
    const globalPrompt = document.getElementById('globalSystemPrompt')?.value || 'You are a helpful AI assistant.';
    const voiceProfile = getVoiceProfile(voiceId);
    
    if (voiceProfile && voiceProfile.personality) {
        return `${globalPrompt}\n\n## Current Character: ${voiceProfile.name || voiceId}\n${voiceProfile.personality}`;
    }
    
    return globalPrompt;
}

// Render voice personalities list in the modal
function renderVoicePersonalitiesList() {
    const container = document.getElementById('voicePersonalitiesList');
    if (!container) return;
    
    const profiles = getVoiceProfiles();
    const profileEntries = Object.entries(profiles);
    
    if (profileEntries.length === 0) {
        container.innerHTML = '<p style="color: var(--text-muted); font-size: 0.8rem; text-align: center; padding: 16px;">No character personalities defined yet.</p>';
        return;
    }
    
    container.innerHTML = profileEntries.map(([voiceId, profile]) => `
        <div class="voice-personality-card" data-voice-id="${voiceId}">
            <div class="voice-personality-header">
                <span class="voice-personality-name">${escapeHtml(profile.name || voiceId)}</span>
                <div class="voice-personality-actions">
                    <button class="edit-personality-btn" onclick="editVoicePersonality('${voiceId}')" title="Edit">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" stroke="currentColor" stroke-width="2"/>
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" stroke="currentColor" stroke-width="2"/>
                        </svg>
                    </button>
                    <button class="delete-personality-btn" onclick="deleteVoicePersonality('${voiceId}')" title="Delete">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                            <path d="M18 6L6 18M6 6L18 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                        </svg>
                    </button>
                </div>
            </div>
            <div class="voice-personality-preview">
                ${escapeHtml(profile.personality?.substring(0, 100) || 'No description')}${profile.personality?.length > 100 ? '...' : ''}
            </div>
            ${profile.style ? `<div class="voice-personality-style">Style: ${escapeHtml(profile.style)}</div>` : ''}
        </div>
    `).join('');
}

// Edit voice personality
function editVoicePersonality(voiceId) {
    const profile = getVoiceProfile(voiceId);
    if (!profile) return;
    
    const container = document.getElementById('voicePersonalitiesList');
    if (!container) return;
    
    // Find the card and replace with edit form
    const cards = container.querySelectorAll('.voice-personality-card');
    cards.forEach(card => {
        card.classList.remove('editing');
    });
    
    const card = container.querySelector(`[data-voice-id="${voiceId}"]`);
    if (card) {
        card.classList.add('editing');
        card.innerHTML = `
            <div class="voice-personality-edit-form">
                <div class="form-group">
                    <label>Character Name</label>
                    <input type="text" class="personality-name-input" value="${escapeHtml(profile.name || '')}" placeholder="e.g., Sofia">
                </div>
                <div class="form-group">
                    <label>Personality & Background</label>
                    <textarea class="personality-text-input" rows="4" placeholder="Describe the character's personality, background, knowledge, mannerisms...">${escapeHtml(profile.personality || '')}</textarea>
                </div>
                <div class="form-group">
                    <label>Speaking Style (optional)</label>
                    <input type="text" class="personality-style-input" value="${escapeHtml(profile.style || '')}" placeholder="e.g., formal, casual, warm, sarcastic">
                </div>
                <div class="form-actions">
                    <button class="btn-secondary" onclick="cancelEditPersonality()">Cancel</button>
                    <button class="btn-primary" onclick="saveEditedPersonality('${voiceId}')">Save</button>
                </div>
            </div>
        `;
    }
}

// Cancel editing
function cancelEditPersonality() {
    renderVoicePersonalitiesList();
}

// Save edited personality
function saveEditedPersonality(voiceId) {
    const card = document.querySelector(`[data-voice-id="${voiceId}"]`);
    if (!card) return;
    
    const name = card.querySelector('.personality-name-input')?.value || 'Unnamed';
    const personality = card.querySelector('.personality-text-input')?.value || '';
    const style = card.querySelector('.personality-style-input')?.value || '';
    
    saveVoiceProfile(voiceId, {
        name,
        personality,
        style,
        updatedAt: new Date().toISOString()
    });
}

// Delete voice personality
function deleteVoicePersonality(voiceId) {
    if (confirm('Delete this character personality?')) {
        deleteVoiceProfile(voiceId);
    }
}

// Initialize voice personalities section
function initVoicePersonalities() {
    const addBtn = document.getElementById('addVoicePersonalityBtn');
    if (addBtn) {
        addBtn.addEventListener('click', addVoicePersonality);
    }
    
    // Populate voice dropdown when voice clone modal opens
    populateVoicePersonalityDropdown();
    
    renderVoicePersonalitiesList();
}

// Populate voice dropdown with available voices
function populateVoicePersonalityDropdown() {
    const select = document.getElementById('voicePersonalitySelect');
    if (!select) return;
    
    // Get voices from ttsSpeaker dropdown in header
    const ttsSpeaker = document.getElementById('ttsSpeaker');
    if (!ttsSpeaker || !ttsSpeaker.options) return;
    
    // Clear existing options except first
    select.innerHTML = '<option value="">-- Select a voice --</option>';
    
    // Add options from ttsSpeaker
    for (let i = 0; i < ttsSpeaker.options.length; i++) {
        const option = ttsSpeaker.options[i];
        if (option.value) {
            const newOption = document.createElement('option');
            newOption.value = option.value;
            newOption.textContent = option.textContent;
            select.appendChild(newOption);
        }
    }
}

// Add new voice personality - uses selected voice from dropdown
function addVoicePersonality() {
    const select = document.getElementById('voicePersonalitySelect');
    let voiceId;
    let name;
    
    if (select && select.value) {
        // Use selected voice from dropdown
        voiceId = select.value;
        name = select.options[select.selectedIndex].textContent;
    } else {
        // Fall back to creating a new one with a timestamp
        voiceId = 'character_' + Date.now();
        name = 'New Character';
    }
    
    // Check if this is Maya and use default personality
    const isMaya = voiceId === 'Maya' || name === 'Maya';
    const defaultPersonality = DEFAULT_VOICE_PROFILES['Maya']?.personality || '';
    
    const profile = {
        name: name,
        personality: isMaya ? defaultPersonality : '',
        style: '',
        createdAt: new Date().toISOString(),
        isDefault: isMaya
    };
    saveVoiceProfile(voiceId, profile);
    editVoicePersonality(voiceId);
}

// Initialize on load
initVoicePersonalities();

// Make functions globally available
window.editVoicePersonality = editVoicePersonality;
window.deleteVoicePersonality = deleteVoicePersonality;
window.cancelEditPersonality = cancelEditPersonality;
window.saveEditedPersonality = saveEditedPersonality;
window.addVoicePersonality = addVoicePersonality;

// ============================================================
// PER-VOICE HISTORY
// ============================================================

const voiceHistoryPrefix = 'chatbot-voice-history-';

function getVoiceHistory(voiceId) {
    const key = voiceHistoryPrefix + voiceId.replace(/[^a-zA-Z0-9]/g, '_');
    const saved = localStorage.getItem(key);
    return saved ? JSON.parse(saved) : [];
}

function saveVoiceHistory(voiceId, messages) {
    const key = voiceHistoryPrefix + voiceId.replace(/[^a-zA-Z0-9]/g, '_');
    // Keep last 100 messages per voice
    const trimmed = messages.slice(-100);
    localStorage.setItem(key, JSON.stringify(trimmed));
}

function addVoiceHistoryMessage(voiceId, role, content) {
    const history = getVoiceHistory(voiceId);
    history.push({
        role,
        content,
        timestamp: new Date().toISOString()
    });
    saveVoiceHistory(voiceId, history);
    return history;
}

function clearVoiceHistory(voiceId) {
    const key = voiceHistoryPrefix + voiceId.replace(/[^a-zA-Z0-9]/g, '_');
    localStorage.removeItem(key);
}

// ============================================================
// AUDIOBOOK LIBRARY
// ============================================================

const audiobookLibraryKey = 'chatbot-audiobook-library';

function getAudiobookLibrary() {
    const saved = localStorage.getItem(audiobookLibraryKey);
    return saved ? JSON.parse(saved) : [];
}

function saveAudiobookToLibrary(audiobook) {
    const library = getAudiobookLibrary();
    audiobook.id = Date.now().toString();
    audiobook.createdAt = new Date().toISOString();
    library.unshift(audiobook);
    // Keep last 20 audiobooks
    const trimmed = library.slice(0, 20);
    localStorage.setItem(audiobookLibraryKey, JSON.stringify(trimmed));
    return audiobook;
}

function deleteAudiobookFromLibrary(id) {
    const library = getAudiobookLibrary();
    const filtered = library.filter(a => a.id !== id);
    localStorage.setItem(audiobookLibraryKey, JSON.stringify(filtered));
}

function renderAudiobookLibrary() {
    const container = document.getElementById('audiobookLibraryList');
    if (!container) return;
    
    const library = getAudiobookLibrary();
    
    if (library.length === 0) {
        container.innerHTML = '<p class="no-audiobooks">No saved audiobooks yet</p>';
        return;
    }
    
    container.innerHTML = library.map(book => `
        <div class="audiobook-library-item" data-id="${book.id}">
            <div class="audiobook-item-info">
                <span class="audiobook-item-title">${escapeHtml(book.title || 'Untitled')}</span>
                <span class="audiobook-item-date">${formatSessionTime(book.createdAt)}</span>
            </div>
            <div class="audiobook-item-actions">
                <button class="play-audiobook-btn" onclick="playAudiobookFromLibrary('${book.id}')" title="Play">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                        <polygon points="5,3 19,12 5,21" fill="currentColor"/>
                    </svg>
                </button>
                <button class="delete-audiobook-btn" onclick="deleteAudiobookFromLibraryUI('${book.id}')" title="Delete">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                        <path d="M3 6H5H21" stroke="currentColor" stroke-width="2"/>
                        <path d="M19 6V20C19 21 18 22 17 22H7C6 22 5 21 5 20V6" stroke="currentColor" stroke-width="2"/>
                    </svg>
                </button>
            </div>
        </div>
    `).join('');
}

function deleteAudiobookFromLibraryUI(id) {
    if (confirm('Delete this audiobook?')) {
        deleteAudiobookFromLibrary(id);
        renderAudiobookLibrary();
    }
}

function playAudiobookFromLibrary(id) {
    const library = getAudiobookLibrary();
    const book = library.find(a => a.id === id);
    if (book && book.audioData) {
        // Decode base64 WAV and play via Web Audio API
        const binaryString = atob(book.audioData);
        const len = binaryString.length;
        const arrayBuffer = new ArrayBuffer(len);
        const uint8 = new Uint8Array(arrayBuffer);
        for (let i = 0; i < len; i++) {
            uint8[i] = binaryString.charCodeAt(i) & 0xFF;
        }
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        ctx.decodeAudioData(arrayBuffer.slice(0), (audioBuffer) => {
            const source = ctx.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(ctx.destination);
            source.onended = () => { ctx.close().catch(() => {}); };
            source.start();
        });
    }
}

// Initialize preset dropdown on load
populatePresetDropdown();

// Initialize voice personalities when modal opens
// Note: voiceCloneModal is already declared in controls.js, so we use getElementById directly
const _voiceCloneModalEl = document.getElementById('voiceCloneModal');
if (_voiceCloneModalEl) {
    const observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            if (mutation.target.classList.contains('active')) {
                populateVoicePersonalityDropdown();
                renderVoicePersonalitiesList();
            }
        });
    });
    observer.observe(_voiceCloneModalEl, { attributes: true, attributeFilter: ['class'] });
}

// Make updateTokenCounterFromText globally available immediately
window.updateTokenCounterFromText = updateTokenCounterFromText;
window.updateTokenCounter = updateTokenCounter;

// Test function to verify token counter works
window.testTokenCounter = function() {
    console.log('[TOKEN TEST] Testing token counter...');
    console.log('[TOKEN TEST] tokenCounterEl:', !!tokenCounterEl);
    console.log('[TOKEN TEST] Current totals:', { totalPromptTokens, totalCompletionTokens });
    
    // Manually update with test data
    updateTokenCounterFromText("Hello, this is a test message from the user.", "This is a test response from the AI assistant.", 1500);
    
    console.log('[TOKEN TEST] After update:', { totalPromptTokens, totalCompletionTokens });
    console.log('[TOKEN TEST] Check if the UI updated in the header.');
};

console.log('[TOKEN] features.js loaded. Test with: window.testTokenCounter()');

// Export functions for use in other modules
window.features = {
    updateTokenCounter,
    updateTokenCounterFromText,
    estimateTokens,
    startTokenRateTracking,
    stopTokenRateTracking,
    resetSessionTokens,
    setStreamReader,
    cancelStreaming,
    getVoiceProfile,
    saveVoiceProfile,
    deleteVoiceProfile,
    getCombinedSystemPrompt,
    getVoiceHistory,
    saveVoiceHistory,
    addVoiceHistoryMessage,
    clearVoiceHistory,
    getAudiobookLibrary,
    saveAudiobookToLibrary,
    deleteAudiobookFromLibrary,
    renderAudiobookLibrary,
    renderVoicePersonalitiesList,
    SYSTEM_PROMPT_PRESETS
};
