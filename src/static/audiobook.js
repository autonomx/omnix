/**
 * Audiobook Feature Module
 * Text-to-speech for documents with multi-speaker support
 */

// Audiobook state
let audiobookState = {
    text: '',
    segments: [],
    speakers: {},
    voiceMapping: {},
    defaultVoices: {
        female: null,
        male: null,
        narrator: null
    },
    audioQueue: [],
    isPlaying: false,
    isGenerating: false,
    currentSegment: 0,
    totalSegments: 0,
    bookId: null,           // persistent book identifier
    directedScript: null,   // result of AI Director
    structuredScript: null  // result of AI Structuring
};

// DOM elements (initialized in initAudiobook)
let audiobookModal, audiobookText, audiobookFile, audiobookAnalyzeBtn;
let audiobookAiStructureBtn, audiobookDirectBtn, audiobookAiStatus;
let audiobookSpeakersSection, audiobookSpeakersList, audiobookGenerateBtn;
let audiobookProgress, audiobookProgressBar, audiobookProgressText;
let audiobookPlayer, audiobookAudio;
let audiobookVoicePanel, audiobookVoicePanelList;

/**
 * Single source of truth for retrieving audiobook text.
 * Checks the textarea first, then falls back to audiobookState.text.
 */
function getAudiobookText() {
    const ui = audiobookText ? audiobookText.value.trim() : '';
    if (ui) return ui;
    return audiobookState.text || '';
}

// Initialize audiobook feature
function initAudiobook() {
    // Get DOM elements
    audiobookModal = document.getElementById('audiobook-modal');
    audiobookText = document.getElementById('audiobook-text');
    audiobookFile = document.getElementById('audiobook-file');
    audiobookAnalyzeBtn = document.getElementById('audiobook-analyze-btn');
    audiobookAiStructureBtn = document.getElementById('audiobook-ai-structure-btn');
    audiobookDirectBtn = document.getElementById('audiobook-direct-btn');
    audiobookAiStatus = document.getElementById('audiobook-ai-status');
    audiobookSpeakersSection = document.getElementById('audiobook-speakers-section');
    audiobookSpeakersList = document.getElementById('audiobook-speakers-list');
    audiobookGenerateBtn = document.getElementById('audiobook-generate-btn');
    audiobookProgress = document.getElementById('audiobook-progress');
    audiobookProgressBar = document.getElementById('audiobook-progress-bar');
    audiobookProgressText = document.getElementById('audiobook-progress-text');
    audiobookPlayer = document.getElementById('audiobook-player');
    audiobookAudio = document.getElementById('audiobook-audio');
    audiobookVoicePanel = document.getElementById('audiobook-voice-panel');
    audiobookVoicePanelList = document.getElementById('audiobook-voice-panel-list');
    
    // Set up event listeners
    if (audiobookAnalyzeBtn) {
        audiobookAnalyzeBtn.addEventListener('click', analyzeAudiobookText);
    }
    if (audiobookAiStructureBtn) {
        audiobookAiStructureBtn.addEventListener('click', aiStructureAudiobookText);
    }
    if (audiobookDirectBtn) {
        audiobookDirectBtn.addEventListener('click', aiDirectScript);
    }
    if (audiobookGenerateBtn) {
        audiobookGenerateBtn.addEventListener('click', generateAudiobook);
    }
    if (audiobookFile) {
        audiobookFile.addEventListener('change', handleAudiobookFileUpload);
    }
    
    console.log('[AUDIOBOOK] Initialized');
}

// Open audiobook modal
function openAudiobookModal() {
    if (audiobookModal) {
        audiobookModal.classList.add('active');
        // Reset state
        resetAudiobookState();
        // Load the audiobook library
        loadAudiobookLibrary();
    }
}

// Close audiobook modal
function closeAudiobookModal() {
    if (audiobookModal) {
        audiobookModal.classList.remove('active');
    }
    // Stop any playing audio
    if (audiobookAudio && audiobookAudio.pause) {
        audiobookAudio.pause();
    }
    audiobookState.isPlaying = false;
}

// Reset audiobook state
function resetAudiobookState() {
    // Stop any active WebSocket connection
    if (audiobookWs) {
        try { audiobookWs.close(); } catch (e) {}
        audiobookWs = null;
    }

    // Tear down any active AudioContext
    if (_streamingAudioCtx) {
        safeCloseAudioContext(_streamingAudioCtx);
        _streamingAudioCtx = null;
    }

    // Stop SSE Web Audio API context (closing kills all scheduled audio)
    if (_sseAudioCtx) {
        safeCloseAudioContext(_sseAudioCtx);
        _sseAudioCtx = null;
    }
    _sseNextPlaybackTime = 0;
    _ssePrevTail = null;

    // Stop any playing SSE audio element (legacy)
    if (streamingAudioElement) {
        try { streamingAudioElement.pause(); streamingAudioElement.currentTime = 0; } catch (e) {}
    }

    // Release combined-audio resources from previous run
    if (combinedAudioUrl) {
        URL.revokeObjectURL(combinedAudioUrl);
    }

    // Reset all streaming / playback module-level variables
    streamingPlaybackInProgress = false;
    streamingAudioIndex = 0;
    streamingShouldShowFullControls = false;
    _wsUserStopped = false;
    _playbackOffset = 0;
    _progressiveAudioChunks = [];
    combinedAudioBlob = null;
    combinedAudioUrl = null;
    combinedAudioElement = null;
    audioSegmentDurations = [];

    audiobookState = {
        text: '',
        segments: [],
        speakers: {},
        voiceMapping: {},
        defaultVoices: {
            female: null,
            male: null,
            narrator: null
        },
        audioQueue: [],
        isPlaying: false,
        isGenerating: false,
        currentSegment: 0,
        totalSegments: 0,
        bookId: null,
        directedScript: null,
        structuredScript: null
    };
    
    if (audiobookText) audiobookText.value = '';
    if (audiobookFile) audiobookFile.value = '';
    if (audiobookSpeakersSection) audiobookSpeakersSection.style.display = 'none';
    if (audiobookProgress) audiobookProgress.style.display = 'none';
    if (audiobookPlayer) {
        audiobookPlayer.style.display = 'none';
        audiobookPlayer.innerHTML = '';
    }
    if (audiobookAiStatus) audiobookAiStatus.style.display = 'none';
    if (audiobookDirectBtn) audiobookDirectBtn.style.display = 'none';
    if (audiobookVoicePanel) audiobookVoicePanel.style.display = 'none';
    if (audiobookSpeakersList) audiobookSpeakersList.innerHTML = '';
    if (audiobookVoicePanelList) audiobookVoicePanelList.innerHTML = '';
}

// ---------------------------------------------------------------------------
// Audiobook library — list & play audio books from resources/data/audiobooks
// ---------------------------------------------------------------------------

/**
 * Fetch the audiobook library from the server and render it in the modal.
 */
async function loadAudiobookLibrary() {
    const container = document.getElementById('audiobook-library-list');
    if (!container) return;

    try {
        const resp = await fetch('/api/audiobook/library');
        const data = await resp.json();
        if (!data.success || !data.books || data.books.length === 0) {
            container.innerHTML = '<p class="no-audiobooks">No audiobooks in the library yet. Add audio files (.mp3, .wav, .ogg, .m4a, .flac, .aac, .wma) to resources/data/audiobooks/</p>';
            return;
        }

        container.innerHTML = data.books.map(book => {
            const sizeMB = (book.size / (1024 * 1024)).toFixed(1);
            return `
                <div class="audiobook-library-item" data-filename="${_escapeAttr(book.filename)}">
                    <div class="audiobook-item-info">
                        <span class="audiobook-item-title">🎧 ${_escapeHtmlLib(book.title)}</span>
                        <span class="audiobook-item-date">${book.type.toUpperCase()} · ${sizeMB} MB</span>
                    </div>
                    <div class="audiobook-item-actions">
                        <button class="play-audiobook-btn" onclick="playAudiobookFromLibraryFile('${_escapeAttr(book.filename)}')" title="Play audiobook">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                                <polygon points="5,3 19,12 5,21" stroke="currentColor" stroke-width="2" fill="currentColor"/>
                            </svg>
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    } catch (e) {
        console.warn('[AUDIOBOOK] Failed to load library:', e);
        container.innerHTML = '<p class="no-audiobooks">Failed to load library</p>';
    }
}

/** Escape HTML for safe rendering in library items. */
function _escapeHtmlLib(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/** Escape a string for use inside an HTML attribute. */
function _escapeAttr(str) {
    return str.replace(/&/g, '&amp;').replace(/'/g, '&#39;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/**
 * Play an audiobook file from the library using the browser audio player.
 */
function playAudiobookFromLibraryFile(filename) {
    if (!filename) return;

    const url = '/api/audiobook/library/' + encodeURIComponent(filename);

    // Remove any existing library audio player
    const existing = document.getElementById('audiobook-library-player');
    if (existing) existing.remove();

    const playerDiv = document.createElement('div');
    playerDiv.id = 'audiobook-library-player';
    playerDiv.style.cssText = 'margin-top: 12px; padding: 12px; background: var(--bg-tertiary); border: 1px solid var(--border-color); border-radius: var(--radius-sm);';
    playerDiv.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
            <span style="font-size: 0.85rem; color: var(--text-primary);">🎧 Now Playing: ${_escapeHtmlLib(filename)}</span>
            <button onclick="this.closest('#audiobook-library-player').remove()" aria-label="Close player" style="background: none; border: none; cursor: pointer; color: var(--text-muted); font-size: 1.1rem;">&times;</button>
        </div>
        <audio controls style="width: 100%;" src="${_escapeAttr(url)}">
            Your browser does not support the audio element.
        </audio>
    `;

    const container = document.getElementById('audiobook-library-section');
    if (container) container.appendChild(playerDiv);
}

// Handle file upload
async function handleAudiobookFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    const filename = file.name.toLowerCase();
    
    if (filename.endsWith('.txt')) {
        const text = await file.text();
        if (audiobookText) {
            audiobookText.value = text;
        }
    } else if (filename.endsWith('.pdf')) {
        // PDF needs server-side processing
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const response = await fetch('/api/audiobook/upload', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                let errMsg = `Server error (${response.status})`;
                try { const errData = await response.json(); errMsg = errData.error || errMsg; } catch (_e) { /* non-JSON error body */ }
                throw new Error(errMsg);
            }
            const data = await response.json();
            if (data.success) {
                // Build best available text source (fallback chain)
                const extractedText =
                    data.full_text ||
                    data.initial_text ||
                    (data.segments ? data.segments.map(s => s.text).join('\n\n') : '');

                // Store segments from initial pages
                audiobookState.segments = data.segments;
                audiobookState.text = extractedText;

                // Populate the textarea so AI Structure / Analyze can read it
                if (audiobookText) {
                    audiobookText.value = extractedText;
                }

                // Auto-assign cloned voices to detected characters
                if (data.characters && data.available_voices) {
                    for (const [charName, score] of Object.entries(data.characters)) {
                        const voiceId = assignClonedVoice(charName, score, data.available_voices);
                        if (voiceId) {
                            audiobookState.voiceMapping[_normalizeKey(charName)] = voiceId;
                        }
                    }
                }

                // Show speakers section
                displaySpeakers(data.speakers, data.segments);

                // Store session_id for lazy page fetching (remaining pages stay server-side)
                if (data.session_id && data.remaining_count > 0) {
                    audiobookState._sessionId = data.session_id;
                    audiobookState._availableVoices = data.available_voices || [];
                    console.log(`[AUDIOBOOK] ${data.total_pages} total pages, ${data.remaining_count} remaining (session: ${data.session_id})`);
                }
            } else {
                alert('Error loading PDF: ' + data.error);
            }
        } catch (error) {
            alert('Error uploading file: ' + error.message);
        }
    }
}

/**
 * Process remaining pages from a PDF upload in the background.
 * Fetches pages lazily from the server using the session_id,
 * then parses each page into segments.
 */
async function processRemainingPages(sessionId) {
    if (!sessionId) return;

    try {
        // Fetch remaining pages from server (lazy loading)
        const fetchRes = await fetch(`/api/audiobook/pages?session_id=${encodeURIComponent(sessionId)}`);
        const fetchData = await fetchRes.json();
        if (!fetchData.success || !fetchData.pages) {
            console.warn('[AUDIOBOOK] Failed to fetch remaining pages:', fetchData.error);
            return;
        }

        for (const pageText of fetchData.pages) {
            // Parse each page into segments via the server
            try {
                const response = await fetch('/api/audiobook/upload', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text: pageText })
                });
                const data = await response.json();
                if (data.success && data.segments) {
                    audiobookState.segments = audiobookState.segments.concat(data.segments);
                    audiobookState.totalSegments = audiobookState.segments.length;

                    // Detect new speakers from this page and update the UI immediately
                    const pageSpeakers = data.speakers || [];
                    const availableVoices = audiobookState._availableVoices || [];
                    let foundNew = false;
                    for (const sp of pageSpeakers) {
                        const key = _normalizeKey(sp);
                        // Use voiceMapping as the single source of truth: skip if the
                        // speaker already has a voice assigned (even if absent from
                        // audiobookState.speakers, which may be populated separately).
                        if (!sp || !sp.trim() || audiobookState.voiceMapping[key]) continue;
                        // Count segments for this speaker across all accumulated pages,
                        // not just the current one, for accurate UI display.
                        const segCount = audiobookState.segments.filter(s => s.speaker === sp).length;
                        audiobookState.speakers[sp] = {
                            name: sp,
                            gender: 'neutral',
                            segment_count: segCount,
                            suggested_voice: '',
                        };
                        // Background pages don't include gender scores, so use a neutral
                        // score which falls back to the full voice pool in assignClonedVoice.
                        const voiceId = assignClonedVoice(sp, { male: 0, female: 0 }, availableVoices);
                        if (voiceId) {
                            audiobookState.voiceMapping[key] = voiceId;
                        }
                        foundNew = true;
                    }
                    if (foundNew) {
                        refreshSpeakersUI();
                    }
                }
            } catch (e) {
                console.warn('[AUDIOBOOK] Error processing remaining page:', e);
            }
        }
    } catch (e) {
        console.warn('[AUDIOBOOK] Error fetching remaining pages:', e);
    }
    console.log('[AUDIOBOOK] Background page processing complete, total segments:', audiobookState.segments.length);
}

// Analyze text for speakers
async function analyzeAudiobookText() {
    const text = getAudiobookText();
    
    if (!text) {
        alert('Please enter or upload some text first');
        return;
    }
    
    audiobookAnalyzeBtn.disabled = true;
    audiobookAnalyzeBtn.textContent = 'Analyzing...';
    
    try {
        const response = await fetch('/api/audiobook/upload', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text })
        });
        
        const data = await response.json();
        
        if (data.success) {
            audiobookState.text = text;
            audiobookState.segments = data.segments;
            
            // Display speakers for voice assignment
            displaySpeakers(data.speakers, data.segments);
        } else {
            alert('Error analyzing text: ' + data.error);
        }
    } catch (error) {
        alert('Error: ' + error.message);
    } finally {
        audiobookAnalyzeBtn.disabled = false;
        audiobookAnalyzeBtn.textContent = 'Analyze Text';
    }
}

// AI Structure: use LLM to parse dialogue intelligently
async function aiStructureAudiobookText() {
    const text = getAudiobookText();
    if (!text) {
        alert('Please enter or upload some text first');
        return;
    }

    if (!audiobookState.bookId) {
        audiobookState.bookId = 'book_' + Date.now();
    }

    _setAiStatus('🤖 AI structuring text — this may take a moment…', true);
    if (audiobookAiStructureBtn) {
        audiobookAiStructureBtn.disabled = true;
        audiobookAiStructureBtn.textContent = '⏳ Structuring…';
    }

    try {
        const response = await fetch('/api/audiobook/ai-structure', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: text,
                title: '',
                book_id: audiobookState.bookId
            })
        });

        if (!response.ok) {
            let errMsg = `Server error (${response.status})`;
            try { const errData = await response.json(); errMsg = errData.error || errMsg; } catch (_e) { /* non-JSON error body */ }
            throw new Error(errMsg);
        }
        const data = await response.json();

        if (data.success) {
            audiobookState.structuredScript = data.structured_script;
            audiobookState.text = text;

            // Flatten all script lines across scenes into segments
            const allLines = [];
            for (const seg of (data.structured_script.segments || [])) {
                for (const line of (seg.script || [])) {
                    allLines.push(line);
                    // Persist voice mapping from AI (normalized key)
                    if (line.voice && line.speaker) {
                        audiobookState.voiceMapping[_normalizeKey(line.speaker)] = line.voice;
                    }
                }
            }
            audiobookState.segments = allLines;

            _setAiStatus(`✅ AI structured ${allLines.length} lines across ${(data.structured_script.segments || []).length} scene(s).`);

            // Show AI Direct button
            if (audiobookDirectBtn) audiobookDirectBtn.style.display = '';

            // Build speaker list from structured characters
            const speakers = (data.structured_script.characters || []).map(c => c.name);
            await displaySpeakers(speakers, allLines);

            // Load persistent voice profiles into the Voice Panel
            await loadVoicePanel(audiobookState.bookId);
        } else {
            _setAiStatus('❌ AI structuring failed: ' + (data.error || 'unknown error'));
        }
    } catch (error) {
        _setAiStatus('❌ Error: ' + error.message);
    } finally {
        if (audiobookAiStructureBtn) {
            audiobookAiStructureBtn.disabled = false;
            audiobookAiStructureBtn.textContent = '🤖 AI Structure';
        }
    }
}

// AI Direct: apply pacing, emotion, emphasis to current segments
async function aiDirectScript() {
    const script = audiobookState.segments;
    if (!script || script.length === 0) {
        alert('Please analyze or AI-structure the text first.');
        return;
    }

    if (!audiobookState.bookId) {
        audiobookState.bookId = 'book_' + Date.now();
    }

    _setAiStatus('🎬 AI Director applying pacing & emotion…', true);
    if (audiobookDirectBtn) {
        audiobookDirectBtn.disabled = true;
        audiobookDirectBtn.textContent = '⏳ Directing…';
    }

    try {
        const response = await fetch('/api/audiobook/direct', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                script: script,
                book_id: audiobookState.bookId
            })
        });

        const data = await response.json();

        if (data.success) {
            audiobookState.directedScript = data.directed_script;
            audiobookState.segments = data.directed_script;

            // Update voice mappings from directed output (normalized key)
            for (const line of data.directed_script) {
                if (line.voice && line.speaker) {
                    audiobookState.voiceMapping[_normalizeKey(line.speaker)] = line.voice;
                }
            }

            const emotions = [...new Set(data.directed_script.map(l => l.emotion).filter(Boolean))];
            _setAiStatus(`✅ AI Director applied. Emotions detected: ${emotions.join(', ') || 'neutral'}.`);
        } else {
            _setAiStatus('❌ AI Direction failed: ' + (data.error || 'unknown error'));
        }
    } catch (error) {
        _setAiStatus('❌ Error: ' + error.message);
    } finally {
        if (audiobookDirectBtn) {
            audiobookDirectBtn.disabled = false;
            audiobookDirectBtn.textContent = '🎬 AI Direct';
        }
    }
}

// Load Voice Identity Memory panel for the current book
async function loadVoicePanel(bookId) {
    if (!audiobookVoicePanel || !audiobookVoicePanelList || !bookId) return;

    try {
        const response = await fetch(`/api/audiobook/books/${encodeURIComponent(bookId)}/voices`);
        const data = await response.json();
        if (!data.success) return;

        const profiles = data.voices || {};
        const availableVoices = data.available_voices || [];

        if (Object.keys(profiles).length === 0) {
            audiobookVoicePanel.style.display = 'none';
            return;
        }

        let html = '';
        for (const [character, profile] of Object.entries(profiles)) {
            const speakerVoice = audiobookState.voiceMapping[_normalizeKey(character)];
            const storedVoice = (typeof profile === 'object' ? profile.voice : profile) || '';
            const currentVoice = speakerVoice || storedVoice;
            html += `<div class="voice-panel-row">`;
            html += `<span class="voice-panel-character">${_escapeHtml(character)}</span>`;
            html += `<select class="voice-panel-select" data-character="${_escapeHtml(character)}" disabled>`;
            html += `<option value="">-- Auto --</option>`;
            availableVoices.forEach(v => {
                const sel = v === currentVoice ? 'selected' : '';
                html += `<option value="${v}" ${sel}>${v}</option>`;
            });
            html += `</select></div>`;
        }

        audiobookVoicePanelList.innerHTML = html;
        audiobookVoicePanel.style.display = 'block';
        syncVoicePanelFromSpeakerSelections();

        const saveBtn = audiobookVoicePanel.querySelector('.voice-panel-save-btn');
        if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.textContent = '🔄 Auto-synced from Individual Speakers';
        }
    } catch (e) {
        console.error('[AUDIOBOOK] Voice panel load error:', e);
    }
}

// Update a single voice panel entry (does not auto-save)
function updateVoicePanelEntry(character, voice) {
    const key = _normalizeKey(character);
    if (voice) {
        audiobookState.voiceMapping[key] = voice;
    } else {
        delete audiobookState.voiceMapping[key];
    }
}

function syncVoicePanelFromSpeakerSelections() {
    if (!audiobookVoicePanelList || !audiobookSpeakersList) return;

    const speakerSelects = audiobookSpeakersList.querySelectorAll('.speaker-voice-select');
    const panelSelects = audiobookVoicePanelList.querySelectorAll('.voice-panel-select');
    if (!speakerSelects.length || !panelSelects.length) return;

    const speakerMap = {};
    speakerSelects.forEach(sel => {
        const speaker = _normalizeKey(sel.dataset.speaker);
        const voice = sel.value;
        if (speaker && voice) speakerMap[speaker] = voice;
    });

    panelSelects.forEach(sel => {
        const character = _normalizeKey(sel.dataset.character);
        if (!character || !speakerMap[character]) return;
        sel.value = speakerMap[character];
    });
}

function scheduleVoiceProfileAutoSave() {
    if (!audiobookState.bookId) return;
    if (voiceProfileSaveTimer) clearTimeout(voiceProfileSaveTimer);
    voiceProfileSaveTimer = setTimeout(() => {
        saveVoiceProfiles();
    }, 500);
}

// Save all voice panel entries to the server
async function saveVoiceProfiles() {
    const bookId = audiobookState.bookId;
    if (!bookId) {
        _setAiStatus('⚠️ No book loaded — please AI-structure your text first.');
        return;
    }

    const selects = audiobookVoicePanelList
        ? audiobookVoicePanelList.querySelectorAll('.voice-panel-select')
        : [];
    const voices = {};
    if (selects.length > 0) {
        selects.forEach(sel => {
            const char = sel.dataset.character;
            const voice = sel.value;
            if (char && voice) voices[char] = voice;
        });
    } else {
        Object.entries(audiobookState.voiceMapping).forEach(([speaker, voice]) => {
            if (speaker && voice) voices[speaker] = voice;
        });
    }

    // Find the save button and show saving state
    const saveBtn = audiobookVoicePanel
        ? audiobookVoicePanel.querySelector('.voice-panel-save-btn')
        : null;
    const resetBtn = () => {
        if (saveBtn) {
            saveBtn.textContent = '🔄 Auto-synced from Individual Speakers';
            saveBtn.disabled = true;
        }
    };
    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.textContent = '⏳ Saving…';
    }

    try {
        const response = await fetch(`/api/audiobook/books/${encodeURIComponent(bookId)}/voices`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ voices })
        });
        const data = await response.json();
        if (data.success) {
            _setAiStatus('💾 Voice profiles saved.');
            if (saveBtn) {
                saveBtn.textContent = '✅ Saved!';
                setTimeout(resetBtn, 2000);
            }
        } else {
            _setAiStatus('❌ Failed to save voice profiles: ' + (data.error || 'unknown error'));
            resetBtn();
        }
    } catch (e) {
        console.error('[AUDIOBOOK] Save voice profiles error:', e);
        _setAiStatus('❌ Error saving voice profiles: ' + e.message);
        resetBtn();
    }
}

// Internal: show/hide AI status message with optional progress bar
function _setAiStatus(msg, showProgress) {
    if (!audiobookAiStatus) return;
    if (!msg) {
        audiobookAiStatus.style.display = 'none';
        audiobookAiStatus.innerHTML = '';
        return;
    }
    let html = `<span>${_escapeHtml(msg)}</span>`;
    if (showProgress) {
        html += `<div class="ai-status-progress"><div class="ai-status-progress-bar"></div></div>`;
    }
    audiobookAiStatus.innerHTML = html;
    audiobookAiStatus.style.display = 'block';
}

// Internal: escape HTML for safe attribute/text insertion
function _escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// Display speakers for voice assignment
async function displaySpeakers(speakers, segments) {
    if (!audiobookSpeakersSection || !audiobookSpeakersList) return;
    
    // Get available voices
    let availableVoices = [];
    try {
        const response = await fetch('/api/tts/speakers');
        const data = await response.json();
        if (data.success) {
            availableVoices = data.speakers.map(s => s.id || s.name);
        }
    } catch (error) {
        console.error('Error fetching voices:', error);
    }
    
    // Detect speakers and get suggestions
    try {
        const response = await fetch('/api/audiobook/speakers/detect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: audiobookState.text })
        });
        
        const data = await response.json();
        if (data.success) {
            audiobookState.speakers = data.speakers;
            availableVoices = data.available_voices;
        }
    } catch (error) {
        console.error('Error detecting speakers:', error);
    }
    
    // Build speakers UI
    let html = '<div class="audiobook-speakers-header">';
    html += '<h4>Speakers Detected</h4>';
    html += '<p>Assign voices to each speaker, or use auto-detected suggestions</p>';
    html += '</div>';
    
    html += '<div class="audiobook-default-voices">';
    html += '<h5>Default Voices</h5>';
    html += '<div class="default-voice-row">';
    html += '<label>Female: </label>';
    html += '<select id="default-voice-female" onchange="updateDefaultVoice(\'female\', this.value)">';
    html += '<option value="">-- Select --</option>';
    availableVoices.forEach(v => {
        html += `<option value="${v}">${v}</option>`;
    });
    html += '</select></div>';
    
    html += '<div class="default-voice-row">';
    html += '<label>Male: </label>';
    html += '<select id="default-voice-male" onchange="updateDefaultVoice(\'male\', this.value)">';
    html += '<option value="">-- Select --</option>';
    availableVoices.forEach(v => {
        html += `<option value="${v}">${v}</option>`;
    });
    html += '</select></div>';
    
    html += '<div class="default-voice-row">';
    html += '<label>Narrator: </label>';
    html += '<select id="default-voice-narrator" onchange="updateDefaultVoice(\'narrator\', this.value)">';
    html += '<option value="">-- Select --</option>';
    availableVoices.forEach(v => {
        html += `<option value="${v}">${v}</option>`;
    });
    html += '</select></div></div>';
    
    // Individual speaker assignments
    html += '<div class="audiobook-speaker-assignments">';
    html += '<h5>Individual Speakers</h5>';
    
    for (const [speakerName, speakerInfo] of Object.entries(audiobookState.speakers)) {
        const gender = speakerInfo.gender || 'neutral';
        const suggested = speakerInfo.suggested_voice || '';
        const segmentCount = speakerInfo.segment_count || 0;
        if (suggested) audiobookState.voiceMapping[_normalizeKey(speakerName)] = suggested;
        
        html += `<div class="speaker-assignment-row" data-gender="${gender}">`;
        html += `<div class="speaker-info">`;
        html += `<span class="speaker-name">${speakerName}</span>`;
        html += `<span class="speaker-meta">${gender} • ${segmentCount} segments</span>`;
        html += `</div>`;
        html += `<select class="speaker-voice-select" data-speaker="${speakerName}" onchange="updateVoiceMapping('${speakerName}', this.value)">`;
        html += '<option value="">-- Auto --</option>';
        availableVoices.forEach(v => {
            const selected = v === suggested ? 'selected' : '';
            html += `<option value="${v}" ${selected}>${v}</option>`;
        });
        html += '</select></div>';
    }
    
    html += '</div>';
    
    // Summary
    html += `<div class="audiobook-summary">`;
    html += `<p><strong>Total Segments:</strong> ${segments.length}</p>`;
    html += `<p><strong>Unique Speakers:</strong> ${Object.keys(audiobookState.speakers).length}</p>`;
    html += `</div>`;
    
    audiobookSpeakersList.innerHTML = html;
    audiobookSpeakersSection.style.display = 'block';
    syncVoicePanelFromSpeakerSelections();
    scheduleVoiceProfileAutoSave();
    
    // Auto-select default voices based on gender detection
    autoSelectDefaultVoices(availableVoices);
}

/**
 * Lightweight refresh of the "Individual Speakers" section.
 * Appends rows for any speakers that are in audiobookState.speakers but
 * not yet rendered in the UI.  Called when background page processing
 * discovers new characters so the user can assign them voices without
 * triggering a full displaySpeakers() re-render (which makes API calls
 * and resets existing voice selections).
 */
function refreshSpeakersUI() {
    if (!audiobookSpeakersList || !audiobookSpeakersSection) return;

    const assignmentsDiv = audiobookSpeakersList.querySelector('.audiobook-speaker-assignments');
    if (!assignmentsDiv) return;

    // Build the set of speaker names already present in the DOM
    const existing = new Set(
        Array.from(assignmentsDiv.querySelectorAll('.speaker-voice-select'))
            .map(s => s.dataset.speaker)
    );

    // Collect available voice ID strings (stored as {id, gender} objects)
    const availableVoices = (audiobookState._availableVoices || []).map(v => v.id || v);

    let added = false;
    for (const [speakerName, speakerInfo] of Object.entries(audiobookState.speakers)) {
        if (existing.has(speakerName)) continue;

        const gender = speakerInfo.gender || 'neutral';
        const segmentCount = speakerInfo.segment_count || 0;
        const currentVoice = audiobookState.voiceMapping[_normalizeKey(speakerName)] || '';

        const row = document.createElement('div');
        row.className = 'speaker-assignment-row';
        row.dataset.gender = gender;
        const optionsHtml = availableVoices.map(v =>
            `<option value="${_escapeHtml(v)}"${v === currentVoice ? ' selected' : ''}>${_escapeHtml(v)}</option>`
        ).join('');
        row.innerHTML =
            `<div class="speaker-info">` +
            `<span class="speaker-name">${_escapeHtml(speakerName)}</span>` +
            `<span class="speaker-meta">${gender} • ${segmentCount} segments</span>` +
            `</div>` +
            `<select class="speaker-voice-select" data-speaker="${_escapeHtml(speakerName)}"` +
            ` onchange="updateVoiceMapping('${_escapeHtml(speakerName)}', this.value)">` +
            `<option value="">-- Auto --</option>${optionsHtml}</select>`;
        assignmentsDiv.appendChild(row);
        added = true;
    }

    if (added) {
        audiobookSpeakersSection.style.display = 'block';
        // Update the summary counts
        const summaryDiv = audiobookSpeakersList.querySelector('.audiobook-summary');
        if (summaryDiv) {
            summaryDiv.innerHTML =
                `<p><strong>Total Segments:</strong> ${audiobookState.segments.length}</p>` +
                `<p><strong>Unique Speakers:</strong> ${Object.keys(audiobookState.speakers).length}</p>`;
        }
        syncVoicePanelFromSpeakerSelections();
    }
}

// Auto-select default voices
function autoSelectDefaultVoices(availableVoices) {
    const femaleVoice = availableVoices.find(v => 
        ['sofia', 'emma', 'olivia', 'her', 'ciri', 'serena', 'sohee'].some(n => v.toLowerCase().includes(n))
    );
    if (femaleVoice) {
        const select = document.getElementById('default-voice-female');
        if (select) {
            select.value = femaleVoice;
            updateDefaultVoice('female', femaleVoice);
        }
    }
    
    // Try to find male voice
    const maleVoice = availableVoices.find(v => 
        ['morgan', 'james', 'nate', 'inigo', 'eric', 'ryan', 'aiden'].some(n => v.toLowerCase().includes(n))
    );
    if (maleVoice) {
        const select = document.getElementById('default-voice-male');
        if (select) {
            select.value = maleVoice;
            updateDefaultVoice('male', maleVoice);
        }
    }
    
    // Narrator defaults to first available or female
    const narratorVoice = femaleVoice || maleVoice || availableVoices[0];
    if (narratorVoice) {
        const select = document.getElementById('default-voice-narrator');
        if (select) {
            select.value = narratorVoice;
            updateDefaultVoice('narrator', narratorVoice);
        }
    }
}

// Update voice mapping
function updateVoiceMapping(speakerName, voiceId) {
    const key = _normalizeKey(speakerName);
    if (voiceId) {
        audiobookState.voiceMapping[key] = voiceId;
    } else {
        delete audiobookState.voiceMapping[key];
    }
    syncVoicePanelFromSpeakerSelections();
    scheduleVoiceProfileAutoSave();
}

// Update default voice
function updateDefaultVoice(gender, voiceId) {
    audiobookState.defaultVoices[gender] = voiceId || null;
}

// Generate audiobook with streaming playback

// Normalize a speaker/character name to a consistent lookup key
function _normalizeKey(name) {
    return (name || '').toLowerCase().trim();
}

// Streaming playback state
let streamingPlaybackInProgress = false;
let streamingAudioIndex = 0;
let streamingAudioElement = null;
// SSE streaming path: reusable AudioContext + timeline scheduling
let _sseAudioCtx = null;
let _sseNextPlaybackTime = 0;
const SSE_TARGET_SAMPLE_RATE = 24000;
const SSE_INITIAL_BUFFER_SEC = 0.25;
// Crossfade state: previous chunk tail for equal-power overlap
let _ssePrevTail = null;
const SSE_CROSSFADE_SAMPLES = 512; // ~21ms @ 24kHz
let streamingShouldShowFullControls = false;
let voiceProfileSaveTimer = null;
const AUDIO_EDGE_FADE_MS = 8;
const MIN_FADE_SAMPLES = 8;
const MAX_FADE_DIVISOR = 4;

// WebSocket audiobook state
let audiobookWs = null;
// Reference to the AudioContext used by the WS streaming path so that
// pauseStreamingAudio / resumeStreamingAudio / stopStreamingAudio can
// control it without needing access to the generateAudiobookWS closure.
let _streamingAudioCtx = null;
// Reference to the AudioWorkletNode used by the WS streaming path.
let _streamingWorkletNode = null;
// Set to true when the user explicitly stops generation so that the
// ws.onclose handler resolves (instead of rejecting) and avoids the
// unintended SSE fallback.
let _wsUserStopped = false;

// Playback position tracking for resume
let _playbackOffset = 0;

// Progressive download state
let _progressiveAudioChunks = [];

/**
 * Safely close an AudioContext, guarding against the "already closed" crash.
 */
function safeCloseAudioContext(ctx) {
    if (ctx && ctx.state !== "closed") {
        ctx.close().catch(() => {});
    }
}

// ---------------------------------------------------------------------------
// Voice assignment from cloned voices with gender
// ---------------------------------------------------------------------------

/** Persistent map: character name → voice_id (kept across chunks). */
const _clonedVoiceMap = {};

/**
 * Determine gender from a character's pronoun score.
 * Requires a margin of ≥2 to decide; otherwise returns "unknown".
 */
function resolveGender(score) {
    if (!score) return "unknown";
    if ((score.male - score.female) >= 2) return "male";
    if ((score.female - score.male) >= 2) return "female";
    return "unknown";
}

/**
 * Simple string hash for deterministic voice assignment.
 * Same character name → same voice every time.
 */
function _hashCode(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = ((hash << 5) - hash) + str.charCodeAt(i);
        hash |= 0; // Convert to 32-bit integer
    }
    return Math.abs(hash);
}

/**
 * Assign a cloned voice to a character based on gender scoring.
 * Uses deterministic hash-based selection so the same character always
 * gets the same voice (no randomness).
 *
 * @param {string} character  - Character name
 * @param {object} score      - { male: number, female: number }
 * @param {Array}  availableVoices - [{ id, gender }, ...]
 * @returns {string|null} voice id or null
 */
function assignClonedVoice(character, score, availableVoices) {
    if (_clonedVoiceMap[character]) return _clonedVoiceMap[character];
    if (!availableVoices || availableVoices.length === 0) return null;

    const gender = resolveGender(score);

    let pool;
    if (gender === "male") {
        pool = availableVoices.filter(v => v.gender === "male");
    } else if (gender === "female") {
        pool = availableVoices.filter(v => v.gender === "female");
    } else {
        pool = availableVoices.filter(v => v.gender === "neutral");
    }

    // Fallback to full pool if no gender match
    if (pool.length === 0) pool = availableVoices;

    const index = _hashCode(character) % pool.length;
    const voice = pool[index];
    _clonedVoiceMap[character] = voice.id;
    return voice.id;
}

/**
 * Update the progressive download link as new audio chunks arrive.
 * Caps memory at 200 chunks to prevent memory blowup on long books.
 */
function updateProgressiveDownload() {
    if (_progressiveAudioChunks.length === 0) return;

    // Cap memory: evict oldest chunks beyond limit
    if (_progressiveAudioChunks.length > 200) {
        _progressiveAudioChunks = _progressiveAudioChunks.slice(-200);
    }

    const blob = new Blob(_progressiveAudioChunks, { type: "audio/wav" });
    const url = URL.createObjectURL(blob);

    let link = document.getElementById("audiobook-progressive-download");
    if (!link) {
        link = document.createElement("a");
        link.id = "audiobook-progressive-download";
        link.className = "btn-secondary";
        link.download = "audiobook_partial.wav";
        link.textContent = "⬇ Download (in progress)";
        const controls = document.querySelector('.audiobook-streaming-controls');
        if (controls) controls.appendChild(link);
    }
    // Revoke old URL to avoid memory leak
    if (link.dataset.blobUrl) URL.revokeObjectURL(link.dataset.blobUrl);
    link.href = url;
    link.dataset.blobUrl = url;
    link.style.display = "inline-block";
}

async function generateAudiobook() {
    if (audiobookState.segments.length === 0) {
        alert('No segments to generate. Please analyze text first.');
        return;
    }
    
    audiobookState.isGenerating = true;
    audiobookState.isPlaying = true;
    audiobookState.audioQueue = [];
    audiobookState.currentSegment = 0;
    audiobookState.totalSegments = audiobookState.segments.length;
    streamingShouldShowFullControls = false;
    _progressiveAudioChunks = [];
    _playbackOffset = 0;

    // Reset combined-audio state so a previous run's data isn't reused
    audioSegmentDurations = [];
    if (combinedAudioUrl) {
        URL.revokeObjectURL(combinedAudioUrl);
        combinedAudioUrl = null;
    }
    combinedAudioBlob = null;
    combinedAudioElement = null;
    
    // Show progress and player immediately
    if (audiobookProgress) audiobookProgress.style.display = 'block';
    showStreamingPlayer();
    
    if (audiobookGenerateBtn) {
        audiobookGenerateBtn.disabled = true;
        audiobookGenerateBtn.textContent = 'Generating...';
    }
    
    updateProgress(0, 'Starting generation...');

    // Kick off background page processing (non-blocking, lazy fetch via session_id)
    if (audiobookState._sessionId) {
        processRemainingPages(audiobookState._sessionId);
    }

    // Try WebSocket first, fall back to SSE
    try {
        await generateAudiobookWS();
    } catch (wsError) {
        console.warn('[AUDIOBOOK] WebSocket generation failed, falling back to SSE:', wsError);
        await generateAudiobookSSE();
    }
    
    audiobookState.isGenerating = false;
    if (audiobookGenerateBtn) {
        audiobookGenerateBtn.disabled = false;
        audiobookGenerateBtn.textContent = 'Generate Audiobook';
    }
}

/**
 * Generate audiobook via WebSocket — streams raw PCM (no base64, no WAV header).
 *
 * Uses scheduled AudioContext playback (not a queue/onended chain) to eliminate
 * audio artifacts between segments.  Subtitles are synchronised against
 * AudioContext.currentTime via a requestAnimationFrame loop.  After generation
 * completes, the accumulated PCM is combined into a WAV blob and the full
 * playback UI (seek bar + download) is shown.
 */
async function generateAudiobookWS() {
    // Unique job identifier sent to the server so it can save a download file
    const jobId = 'ab_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/audiobook`;

    _wsUserStopped = false;

    return new Promise((resolve, reject) => {
        let ws;
        try {
            ws = new WebSocket(wsUrl);
        } catch (e) {
            reject(e);
            return;
        }
        ws.binaryType = 'arraybuffer';
        audiobookWs = ws;

        // ── AudioWorklet streaming state ──────────────────────────────────
        let audioCtx = null;
        let workletNode = null;
        const SAMPLE_RATE = 24000;
        let totalSamplesPushed = 0;
        /** Buffered duration in seconds — updated from worklet progress reports. */
        let bufferedSeconds = 0;
        const MAX_BUFFER_SECONDS = 8;
        /** Overflow queue: chunks that couldn't be pushed due to backpressure. */
        const overflowQueue = [];
        /** Incremental sample count in overflowQueue for O(1) duration checks. */
        let overflowQueueSamples = 0;
        /** Maximum overflow queue duration in seconds before warning (no audio is dropped). */
        const MAX_QUEUE_SECONDS = 20;
        /** Cap subtitle interpolation to 0.1 seconds (100ms) so transcript can't run ahead on delayed progress messages. */
        const MAX_INTERPOLATION_SECONDS = 0.1;
        let overflowQueueWarningEmitted = false;
        /** Total samples played, reported by the AudioWorklet. */
        let samplesPlayedByWorklet = 0;
        /** Timestamp of last worklet progress report, for playback interpolation. */
        let lastProgressTimestamp = 0;

        // ── PCM accumulation (for final WAV download) ─────────────────────
        /** All raw Int16Array chunks received during this session. */
        const allPcmChunks = [];

        // ── Segment timing for subtitle sync ─────────────────────────────
        /**
         * Segments whose scheduled audio window has been fully determined.
         * Each entry: { index, text, speaker, voiceUsed, startTime, endTime }
         */
        const scheduledSegments = [];
        /** The segment currently being scheduled (audio not yet fully received). */
        let pendingSegMeta = null;
        let subtitleRafId = null;
        let finished = false;
        let playbackStarted = false;

        // ── Helpers ───────────────────────────────────────────────────────

        /**
         * Concatenate all accumulated Int16Array chunks into a single WAV Blob
         * and store it in the module-level combinedAudioBlob / combinedAudioUrl.
         * No-op if no chunks have been received or a blob was already built.
         */
        function _buildWavBlobFromChunks() {
            if (allPcmChunks.length === 0 || combinedAudioBlob) return;
            let totalLen = 0;
            for (const c of allPcmChunks) totalLen += c.length;
            const combined = new Int16Array(totalLen);
            let offset = 0;
            for (const c of allPcmChunks) {
                combined.set(c, offset);
                offset += c.length;
            }
            const pcmBytes = new Uint8Array(combined.buffer);
            const wavBuffer = createWavBufferFromPcm(pcmBytes, SAMPLE_RATE);
            combinedAudioBlob = new Blob([wavBuffer], { type: 'audio/wav' });
            combinedAudioUrl = URL.createObjectURL(combinedAudioBlob);
        }

        async function initAudio() {
            if (!audioCtx) {
                audioCtx = new (window.AudioContext || window.webkitAudioContext)({
                    sampleRate: SAMPLE_RATE,
                    latencyHint: 'interactive',
                });
                _streamingAudioCtx = audioCtx;

                await audioCtx.audioWorklet.addModule('/static/voice/streamProcessor.js');
                workletNode = new AudioWorkletNode(audioCtx, 'stream-processor', {
                    processorOptions: { sampleRate: SAMPLE_RATE }
                });
                workletNode.connect(audioCtx.destination);
                _streamingWorkletNode = workletNode;

                // Receive playback progress and buffer level from the AudioWorklet
                workletNode.port.onmessage = (e) => {
                    if (e.data.type === 'progress') {
                        samplesPlayedByWorklet = e.data.samplesPlayed;
                        lastProgressTimestamp = audioCtx ? audioCtx.currentTime : 0;
                        bufferedSeconds = e.data.availableSamples / SAMPLE_RATE;
                        drainOverflowQueue();
                    }
                };
            }
            if (audioCtx.state === 'suspended') {
                await audioCtx.resume();
            }
        }

        /**
         * Push a PCM int16 audio chunk into the AudioWorklet ring buffer.
         * Handles int16→float32 conversion, validation, and backpressure
         * via overflow queue.
         * Returns true if the chunk was pushed immediately, false if queued
         * or not accepted.
         *
         * Note: No per-chunk crossfade is applied here.  The server sends
         * continuous PCM frames within each sentence-level segment, so
         * consecutive chunks are already seamless.  Sentence boundaries
         * have natural pauses from the TTS model and the AudioWorklet's
         * underrun recovery handles any gaps smoothly.
         */
        function pushAudioChunk(pcm16Array) {
            if (!audioCtx || !workletNode) return false;

            // Convert int16 → float32, validate (skip corrupt chunks with non-finite
            // values), and hard-clamp to [-1, 1] — all in a single pass for efficiency.
            const float32 = new Float32Array(pcm16Array.length);
            for (let i = 0; i < pcm16Array.length; i++) {
                const sample = pcm16Array[i] / 32768.0;
                if (!Number.isFinite(sample)) {
                    console.warn('[AUDIOBOOK-WS] Skipping corrupt (non-finite) audio chunk');
                    return false;
                }
                float32[i] = sample > 1 ? 1 : sample < -1 ? -1 : sample;
            }

            // Track segment timing (always, even if chunk is queued)
            const chunkStartTime = totalSamplesPushed / SAMPLE_RATE;
            totalSamplesPushed += float32.length;

            // Latch the start time for the first chunk of the current segment
            if (pendingSegMeta !== null && pendingSegMeta.startTime < 0) {
                pendingSegMeta.startTime = chunkStartTime;
            }

            // Backpressure: queue chunks instead of dropping them
            if (bufferedSeconds > MAX_BUFFER_SECONDS) {
                overflowQueue.push(float32);
                overflowQueueSamples += float32.length;
                // Trim oldest if overflow queue exceeds MAX_QUEUE_SECONDS
                trimOverflowQueue();
                return false;
            }

            const duration = float32.length / SAMPLE_RATE;
            bufferedSeconds += duration;

            workletNode.port.postMessage({
                type: 'push',
                samples: float32,
            });
            return true;
        }

        /**
         * Trim the overflow queue if total duration exceeds MAX_QUEUE_SECONDS
         * to prevent unbounded memory growth.  Uses incremental
         * overflowQueueSamples counter for O(1) duration checks.
         */
        function trimOverflowQueue() {
            if (overflowQueueSamples / SAMPLE_RATE > MAX_QUEUE_SECONDS && !overflowQueueWarningEmitted) {
                overflowQueueWarningEmitted = true;
                console.warn('[AUDIOBOOK-WS] Overflow queue exceeded limit; preserving queued audio to avoid word skips');
            }
        }

        /**
         * Drain the overflow queue by pushing queued chunks to the worklet
         * until the buffer is full again.  Checks each chunk's size before
         * pushing to avoid overshooting the buffer limit.  A small allowance
         * prevents starvation when chunks are large relative to remaining
         * buffer space.
         */
        const DRAIN_ALLOWANCE = 0.25; // seconds
        function drainOverflowQueue() {
            while (
                overflowQueue.length > 0 &&
                bufferedSeconds + (overflowQueue[0].length / SAMPLE_RATE) <= MAX_BUFFER_SECONDS + DRAIN_ALLOWANCE
            ) {
                const chunk = overflowQueue.shift();
                overflowQueueSamples -= chunk.length;
                const duration = chunk.length / SAMPLE_RATE;
                bufferedSeconds += duration;
                workletNode.port.postMessage({
                    type: 'push',
                    samples: chunk,
                });
            }
        }

        function finalizeCurrentSegment() {
            if (pendingSegMeta !== null) {
                if (pendingSegMeta.startTime >= 0) {
                    pendingSegMeta.endTime = totalSamplesPushed / SAMPLE_RATE;
                    scheduledSegments.push(pendingSegMeta);
                }
                pendingSegMeta = null;
            }
        }

        /**
         * requestAnimationFrame loop that updates the subtitle display to match
         * the currently playing audio based on the worklet's reported playback
         * position (samples actually played).
         * Interpolates between progress reports for smooth 60fps subtitle movement.
         * Also updates _playbackOffset based on segment timing for accurate resume.
         */
        function updateSubtitlesLoop() {
            if (!audioCtx) return;
            const baseTime = (samplesPlayedByWorklet || 0) / SAMPLE_RATE;
            const elapsed = lastProgressTimestamp > 0 ? (audioCtx.currentTime - lastProgressTimestamp) : 0;
            const elapsedClamped = Math.max(0, elapsed);
            const interpolationCap = Math.min(MAX_INTERPOLATION_SECONDS, bufferedSeconds);
            const interpolated = Math.min(elapsedClamped, interpolationCap);
            const playbackTime = baseTime + interpolated;
            for (const seg of scheduledSegments) {
                if (playbackTime >= seg.startTime && playbackTime < seg.endTime) {
                    updateSegmentInfo(seg);
                    // Track playback position using segment timeline
                    _playbackOffset = seg.startTime;
                    break;
                }
            }
            if (!finished || samplesPlayedByWorklet < totalSamplesPushed) {
                subtitleRafId = requestAnimationFrame(updateSubtitlesLoop);
            }
        }

        /**
         * Build a WAV blob from the accumulated PCM chunks, populate the
         * shared state that showFullPlaybackControls() needs, then show it.
         */
        function buildAndShowFinalPlayer() {
            if (allPcmChunks.length === 0) {
                resolve();
                return;
            }

            // Build WAV blob only if not already built eagerly in 'done' handler
            _buildWavBlobFromChunks();

            // Populate per-segment duration list used by updateSegmentInfoForTime()
            audioSegmentDurations = scheduledSegments.map(seg =>
                Math.max(0, seg.endTime - seg.startTime));

            // Populate audiobookState.audioQueue with segment metadata for the
            // time-based subtitle loop inside the full player
            audiobookState.audioQueue = scheduledSegments.map(seg => ({
                speaker: seg.speaker,
                text: seg.text,
                voiceUsed: seg.voiceUsed,
            }));

            // Compute where in the audio the streaming playback currently is so
            // that the full player can seek to the same position.
            let seekToSeconds = (samplesPlayedByWorklet || 0) / SAMPLE_RATE;
            const wasPlaying = audiobookState.isPlaying;

            // Stop the subtitle RAF loop and tear down the AudioWorklet and
            // AudioContext — the full player uses a plain <audio> element instead.
            if (subtitleRafId) {
                cancelAnimationFrame(subtitleRafId);
                subtitleRafId = null;
            }
            if (workletNode) {
                workletNode.disconnect();
                workletNode = null;
                _streamingWorkletNode = null;
            }
            if (audioCtx) {
                safeCloseAudioContext(audioCtx);
                audioCtx = null;
                _streamingAudioCtx = null;
            }

            streamingPlaybackInProgress = false;
            showFullPlaybackControls(seekToSeconds, wasPlaying);
            resolve();
        }

        // ── WebSocket timeout ─────────────────────────────────────────────
        const timeout = setTimeout(() => {
            if (ws.readyState !== WebSocket.OPEN) {
                ws.close();
                reject(new Error('WebSocket connection timeout'));
            }
        }, 5000);

        // ── WebSocket events ──────────────────────────────────────────────
        ws.onopen = () => {
            clearTimeout(timeout);
            console.log('[AUDIOBOOK-WS] Connected, jobId:', jobId);
            ws.send(JSON.stringify({
                type: 'start',
                segments: audiobookState.segments,
                voice_mapping: audiobookState.voiceMapping,
                default_voices: audiobookState.defaultVoices,
                job_id: jobId,
            }));
        };

        ws.onmessage = async (event) => {
            if (event.data instanceof ArrayBuffer) {
                // ── Binary: raw PCM int16 chunk ───────────────────────────
                // Handle odd-length buffers by zero-padding instead of dropping
                let pcmBuffer = event.data;
                if (pcmBuffer.byteLength % 2 !== 0) {
                    const padded = new Uint8Array(pcmBuffer.byteLength + 1);
                    padded.set(new Uint8Array(pcmBuffer));
                    padded[pcmBuffer.byteLength] = 0;
                    pcmBuffer = padded.buffer;
                }
                const pcm16 = new Int16Array(pcmBuffer);
                // Skip chunks that are too short to be valid audio
                if (pcm16.length < 100) {
                    console.warn('[AUDIOBOOK-WS] Skipping too-short chunk:', pcm16.length, 'samples');
                    return;
                }
                await initAudio();
                allPcmChunks.push(pcm16);
                if (!pushAudioChunk(pcm16)) {
                    console.warn('[AUDIOBOOK-WS] pushAudioChunk returned false — chunk queued or lost');
                }

                if (!playbackStarted) {
                    playbackStarted = true;
                    streamingPlaybackInProgress = true;
                    updateSubtitlesLoop();
                }
            } else {
                // ── JSON control message ──────────────────────────────────
                try {
                    const data = JSON.parse(event.data);

                    switch (data.type) {
                        case 'start':
                            // Server may send total_segments for sentence-level
                            // progress when segments differ from the original
                            // dialogue-level count.
                            if (data.total_segments !== undefined && data.total_segments !== null) {
                                audiobookState.totalSegments = data.total_segments;
                            }
                            updateStreamingStatus('Streaming audio…');
                            break;

                        case 'segment': {
                            // Finalise previous segment's time window
                            finalizeCurrentSegment();

                            const idx = data.index;
                            audiobookState.currentSegment = idx + 1;
                            const pct = Math.round(
                                (audiobookState.currentSegment / audiobookState.totalSegments) * 100
                            );
                            updateProgress(pct,
                                `Generated ${audiobookState.currentSegment}/${audiobookState.totalSegments} segments`);

                            // Start tracking the new segment; startTime latched on first chunk
                            const srcSeg = idx < audiobookState.segments.length
                                ? audiobookState.segments[idx] : {};
                            pendingSegMeta = {
                                index: idx,
                                text: data.text || srcSeg.text || '',
                                speaker: data.speaker || srcSeg.speaker || 'Narrator',
                                voiceUsed: data.voice || srcSeg.voice || undefined,
                                startTime: -1,   // latched when first chunk arrives
                                endTime: -1,
                            };
                            break;
                        }

                        case 'done':
                            finalizeCurrentSegment();
                            updateProgress(100, 'Generation complete!');
                            audiobookState.isGenerating = false;
                            finished = true;
                            ws.close();

                            // Build WAV blob immediately so the download button can be
                            // shown right away, before the audio finishes draining.
                            _buildWavBlobFromChunks();
                            if (combinedAudioBlob) {
                                _showEarlyDownloadButton();
                            }

                            // If the user has paused (AudioContext suspended) or stopped,
                            // show the full player immediately — the AudioContext will
                            // never drain on its own when suspended.
                            if (!audiobookState.isPlaying || (audioCtx && audioCtx.state === 'suspended')) {
                                buildAndShowFinalPlayer();
                            } else if (bufferedSeconds > 0) {
                                // Wait for buffered audio to finish playing, then build
                                // the full player.  The extra 600 ms gives the worklet
                                // time to drain the last samples.
                                const waitMs = bufferedSeconds * 1000 + 600;
                                updateStreamingStatus('Finishing playback…');
                                setTimeout(buildAndShowFinalPlayer, waitMs);
                            } else {
                                buildAndShowFinalPlayer();
                            }
                            break;

                        case 'error':
                            console.error('[AUDIOBOOK-WS] Server error:', data.message);
                            updateProgress(-1, `Error: ${data.message}`);
                            finished = true;
                            ws.close();
                            reject(new Error(data.message));
                            break;
                    }
                } catch (e) {
                    console.error('[AUDIOBOOK-WS] Parse error:', e);
                }
            }
        };

        ws.onerror = (err) => {
            clearTimeout(timeout);
            console.error('[AUDIOBOOK-WS] WebSocket error:', err);
            reject(new Error('WebSocket error'));
        };

        ws.onclose = () => {
            audiobookWs = null;
            if (!finished) {
                if (_wsUserStopped) {
                    // User intentionally stopped generation.  Build the full player
                    // from whatever PCM we received so far — resolve so generateAudiobook
                    // doesn't fall back to SSE.
                    if (allPcmChunks.length > 0) {
                        _buildWavBlobFromChunks();
                        if (combinedAudioBlob) _showEarlyDownloadButton();

                        audioSegmentDurations = scheduledSegments.map(seg =>
                            Math.max(0, seg.endTime - seg.startTime));
                        audiobookState.audioQueue = scheduledSegments.map(seg => ({
                            speaker: seg.speaker,
                            text: seg.text,
                            voiceUsed: seg.voiceUsed,
                        }));

                        if (subtitleRafId) {
                            cancelAnimationFrame(subtitleRafId);
                            subtitleRafId = null;
                        }
                        // audioCtx / workletNode already closed by stopStreamingAudio
                        workletNode = null;
                        _streamingWorkletNode = null;
                        audioCtx = null;
                        _streamingAudioCtx = null;

                        streamingPlaybackInProgress = false;
                        if (combinedAudioBlob && audiobookState.audioQueue.length > 0) {
                            showFullPlaybackControls(0, false);
                        }
                    }
                    resolve();
                } else {
                    reject(new Error('WebSocket closed unexpectedly'));
                }
            }
        };
    });
}

/**
 * Generate audiobook via SSE (legacy fallback).
 * Uses /api/audiobook/generate with base64-encoded audio.
 */
async function generateAudiobookSSE() {
    try {
        const response = await fetch('/api/audiobook/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                segments: audiobookState.segments,
                voice_mapping: audiobookState.voiceMapping,
                default_voices: audiobookState.defaultVoices
            })
        });
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            
            // Process SSE events
            const events = buffer.split('\n\n');
            buffer = events.pop() || '';
            
            for (const event of events) {
                const lines = event.split('\n');
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const dataStr = line.slice(6);
                        if (!dataStr.trim()) continue;
                        
                        try {
                            const data = JSON.parse(dataStr);
                            
                            if (data.type === 'audio') {
                                // Add to queue
                                audiobookState.audioQueue.push({
                                    audio: data.audio,
                                    sampleRate: data.sample_rate,
                                    speaker: data.speaker,
                                    text: data.text,
                                    voiceUsed: data.voice_used,
                                    index: data.segment_index
                                });
                                
                                audiobookState.currentSegment = data.segment_index + 1;
                                const percent = Math.round((audiobookState.currentSegment / audiobookState.totalSegments) * 100);
                                updateProgress(percent, `Generated ${audiobookState.currentSegment}/${audiobookState.totalSegments} segments`);
                                
                                // Start playing if not already playing
                                if (!streamingPlaybackInProgress && audiobookState.isPlaying) {
                                    playStreamingAudio();
                                }
                                
                            } else if (data.type === 'done') {
                                updateProgress(100, 'Generation complete!');
                                updateStreamingStatus('Finishing playback...');
                                audiobookState.isGenerating = false;
                                streamingShouldShowFullControls = true;
                                if (!streamingPlaybackInProgress && streamingAudioIndex >= audiobookState.audioQueue.length && audiobookState.audioQueue.length > 0) {
                                    showFullPlaybackControls();
                                }
                                
                            } else if (data.type === 'job') {
                                // Download URL is ready — show button early (file written
                                // on server once generation completes).
                                if (data.download_url) {
                                    _showEarlyServerDownloadButton(data.download_url);
                                }

                            } else if (data.type === 'error') {
                                console.error('Audiobook error:', data.error);
                                const errorMsg = data.error || 'Unknown error';
                                if (data.code === 'TTS_UNAVAILABLE') {
                                    updateProgress(-1, 'TTS is not available. Please check that the TTS provider is configured in settings and try again.');
                                    stopStreamingAudio();
                                } else {
                                    updateProgress(-1, `Error: ${errorMsg}`);
                                }
                            }
                        } catch (e) {
                            console.error('Parse error:', e);
                        }
                    }
                }
            }
        }
        
    } catch (error) {
        console.error('SSE generation error:', error);
        updateProgress(-1, `Error: ${error.message}`);
    }
}

// Combined audio for playback controls
let combinedAudioBlob = null;
let combinedAudioUrl = null;
let combinedAudioElement = null;
let audioSegmentDurations = []; // Track duration of each segment for seeking

/**
 * Show a download button immediately (WS path — client-side blob already built).
 * Called as soon as the 'done' WS message arrives, before audio finishes draining.
 */
function _showEarlyDownloadButton() {
    if (!audiobookPlayer || !combinedAudioBlob) return;
    if (document.getElementById('audiobook-early-download')) return;
    const div = document.createElement('div');
    div.id = 'audiobook-early-download';
    div.className = 'audiobook-actions-row';
    div.innerHTML = '<button class="btn-primary" onclick="downloadAudiobook()">⬇ Download Audiobook</button>';
    audiobookPlayer.appendChild(div);
}

/**
 * Show a server-side download link immediately (SSE path — file written at end
 * of generation, but URL is known upfront so we can show the button early).
 */
function _showEarlyServerDownloadButton(downloadUrl) {
    if (!audiobookPlayer) return;
    const existing = document.getElementById('audiobook-early-download');
    if (existing) {
        const anchor = existing.querySelector('a');
        if (anchor) anchor.href = downloadUrl;
        return;
    }
    const div = document.createElement('div');
    div.id = 'audiobook-early-download';
    div.className = 'audiobook-actions-row';
    div.innerHTML = `<a class="btn-primary" href="${downloadUrl}" download="audiobook.wav">⬇ Download Audiobook</a>`;
    audiobookPlayer.appendChild(div);
}

// Show streaming player (minimal controls that appear immediately)
function showStreamingPlayer() {
    if (!audiobookPlayer) return;
    
    audiobookPlayer.style.display = 'block';
    
    let html = '<div class="audiobook-controls">';
    html += '<button id="audiobook-pause-btn" class="btn-secondary" onclick="pauseStreamingAudio()">⏸ Pause</button>';
    html += '<button id="audiobook-resume-btn" class="btn-primary" onclick="resumeStreamingAudio()" style="display:none;">▶ Resume</button>';
    html += '<button class="btn-secondary" onclick="stopStreamingAudio()">⏹ Stop</button>';
    html += '<span id="audiobook-status">Generating and streaming...</span>';
    html += '</div>';
    
    // Show segment info
    html += '<div class="audiobook-segment-info" id="audiobook-segment-info">';
    html += '<p>Preparing first audio segment...</p>';
    html += '</div>';
    
    audiobookPlayer.innerHTML = html;
    
    streamingPlaybackInProgress = false;
    streamingAudioIndex = 0;
}

// Play streaming audio - schedules chunks on the global timeline as they arrive
async function playStreamingAudio() {
    streamingPlaybackInProgress = true;
    
    while (audiobookState.isPlaying) {
        // Wait for next chunk if not available yet
        if (streamingAudioIndex >= audiobookState.audioQueue.length) {
            // If generation is done and we've played everything, stop
            if (!audiobookState.isGenerating) {
                updateStreamingStatus('Playback complete!');
                break;
            }
            // Wait for next chunk
            await new Promise(resolve => setTimeout(resolve, 100));
            continue;
        }
        
        const segment = audiobookState.audioQueue[streamingAudioIndex];
        
        // Update status
        updateStreamingStatus(`Playing ${streamingAudioIndex + 1}/${audiobookState.totalSegments}`);
        updateSegmentInfo(segment);
        
        // Schedule the segment on the timeline (fire-and-forget, no await)
        playAudioSegment(segment);
        streamingAudioIndex++;
    }
    
    streamingPlaybackInProgress = false;
    if (streamingShouldShowFullControls && audiobookState.audioQueue.length > 0 && audiobookState.isPlaying) {
        streamingShouldShowFullControls = false;
        showFullPlaybackControls();
    }
}

// Schedule a single audio segment on the global timeline (fire-and-forget)
function playAudioSegment(segment) {
    try {
        // Decode base64 PCM to raw bytes
        const binaryString = atob(segment.audio);
        const len = binaryString.length;
        const pcmBytes = new Uint8Array(len);
        for (let i = 0; i < len; i++) {
            pcmBytes[i] = binaryString.charCodeAt(i) & 0xFF;
        }

        // Convert Int16 PCM to Float32
        const totalSamples = Math.floor(pcmBytes.length / 2);
        const byteView = new DataView(pcmBytes.buffer, pcmBytes.byteOffset, pcmBytes.byteLength);
        let float32 = new Float32Array(totalSamples);
        for (let i = 0; i < totalSamples; i++) {
            float32[i] = byteView.getInt16(i * 2, true) / 32768.0;
        }

        // Skip crossfade for very small chunks (avoid slicing to empty)
        if (float32.length < 128) {
            _ssePrevTail = float32.length > 0 ? new Float32Array(float32) : null;
            // fall through to schedule the tiny chunk as-is
        } else {
            // Equal-power crossfade: blend start of this chunk with tail of previous chunk,
            // then trim the overlapped region to prevent energy duplication
            if (_ssePrevTail && float32.length > 0) {
                const overlap = Math.min(_ssePrevTail.length, float32.length, SSE_CROSSFADE_SAMPLES);
                if (overlap > 0) {
                    for (let i = 0; i < overlap; i++) {
                        const t = i / overlap;
                        const fadeOut = Math.cos(t * Math.PI * 0.5);
                        const fadeIn  = Math.sin(t * Math.PI * 0.5);
                        float32[i] = _ssePrevTail[i] * fadeOut + float32[i] * fadeIn;
                    }
                    // Trim overlapped portion to prevent energy duplication
                    float32 = float32.slice(overlap);
                }
            }

            // Store tail safely for next crossfade (after trimming)
            const tailLen = Math.min(SSE_CROSSFADE_SAMPLES, float32.length);
            _ssePrevTail = tailLen > 0 ? float32.slice(float32.length - tailLen) : null;
        }

        if (segment.sampleRate !== SSE_TARGET_SAMPLE_RATE) {
            console.warn('[AUDIOBOOK-SSE] Sample rate mismatch:', segment.sampleRate,
                         'expected:', SSE_TARGET_SAMPLE_RATE);
        }

        // Lazily create a shared AudioContext (never recreate mid-stream)
        if (!_sseAudioCtx || _sseAudioCtx.state === 'closed') {
            _sseAudioCtx = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: SSE_TARGET_SAMPLE_RATE,
                latencyHint: 'interactive'
            });
            _sseNextPlaybackTime = _sseAudioCtx.currentTime + SSE_INITIAL_BUFFER_SEC;
        }
        if (_sseAudioCtx.state === 'suspended') {
            _sseAudioCtx.resume();
        }

        const audioBuffer = _sseAudioCtx.createBuffer(1, float32.length, SSE_TARGET_SAMPLE_RATE);
        audioBuffer.getChannelData(0).set(float32);

        const source = _sseAudioCtx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(_sseAudioCtx.destination);

        // Underrun protection: if timeline has fallen behind, jump ahead
        const now = _sseAudioCtx.currentTime;
        if (_sseNextPlaybackTime < now) {
            _sseNextPlaybackTime = now + 0.05;
        }

        // Schedule on the global timeline (gapless)
        source.start(_sseNextPlaybackTime);
        _sseNextPlaybackTime += audioBuffer.duration;

    } catch (error) {
        console.error('[AUDIOBOOK-SSE] Error scheduling segment:', error);
    }
}

// Update streaming status
function updateStreamingStatus(text) {
    const statusEl = document.getElementById('audiobook-status');
    if (statusEl) statusEl.textContent = text;
}

// Update segment info display
function updateSegmentInfo(segment) {
    const infoEl = document.getElementById('audiobook-segment-info');
    if (infoEl) {
        infoEl.innerHTML = `
            <p><strong>Speaker:</strong> ${segment.speaker || 'Unknown'}</p>
            <p><strong>Voice:</strong> ${segment.voiceUsed || 'Default'}</p>
            <p><strong>Text:</strong> ${segment.text || ''}</p>
        `;
    }
}

// Pause streaming audio
function pauseStreamingAudio() {
    audiobookState.isPlaying = false;

    // Track current playback position using segment timeline (not AudioContext.currentTime)
    if (_streamingAudioCtx && _streamingAudioCtx.state === 'running') {
        // Find the segment that's currently playing and use its startTime
        // as the canonical playback offset in the audio timeline
        const now = _streamingAudioCtx.currentTime;
        // _playbackOffset is set during subtitle updates — see generateAudiobookWS
    }

    // WS path: suspend the AudioContext so scheduled chunks stop playing
    if (_streamingAudioCtx && _streamingAudioCtx.state === 'running') {
        _streamingAudioCtx.suspend().catch(e =>
            console.warn('[AUDIOBOOK] AudioContext suspend failed:', e));
    }

    // SSE path: suspend the AudioContext
    if (_sseAudioCtx && _sseAudioCtx.state === 'running') {
        _sseAudioCtx.suspend().catch(e =>
            console.warn('[AUDIOBOOK] SSE AudioContext suspend failed:', e));
    }
    // Legacy SSE path: pause the <audio> element
    if (streamingAudioElement) {
        streamingAudioElement.pause();
    }
    
    const pauseBtn = document.getElementById('audiobook-pause-btn');
    const resumeBtn = document.getElementById('audiobook-resume-btn');
    if (pauseBtn) pauseBtn.style.display = 'none';
    if (resumeBtn) resumeBtn.style.display = 'inline-block';
    
    updateStreamingStatus('Paused');
}

// Resume streaming audio
function resumeStreamingAudio() {
    audiobookState.isPlaying = true;

    // WS path: resume the AudioContext
    if (_streamingAudioCtx && _streamingAudioCtx.state === 'suspended') {
        _streamingAudioCtx.resume().catch(e =>
            console.warn('[AUDIOBOOK] AudioContext resume failed:', e));
    }
    
    const pauseBtn = document.getElementById('audiobook-pause-btn');
    const resumeBtn = document.getElementById('audiobook-resume-btn');
    if (pauseBtn) pauseBtn.style.display = 'inline-block';
    if (resumeBtn) resumeBtn.style.display = 'none';
    
    // SSE path: resume the AudioContext
    if (_sseAudioCtx && _sseAudioCtx.state === 'suspended') {
        _sseAudioCtx.resume().catch(e =>
            console.warn('[AUDIOBOOK] SSE AudioContext resume failed:', e));
    }
    // Legacy SSE path: resume playback (the <audio> element maintains its own position)
    if (streamingAudioElement && streamingAudioElement.paused) {
        streamingAudioElement.play();
    }
    
    // SSE path: continue streaming playback loop
    if (!streamingPlaybackInProgress) {
        playStreamingAudio();
    }
}

// Stop streaming audio
function stopStreamingAudio() {
    audiobookState.isPlaying = false;
    // Stop generation: WS is closed so the server stops sending.
    // (pauseStreamingAudio deliberately leaves isGenerating unchanged so the
    // server continues generating while audio is suspended.)
    audiobookState.isGenerating = false;
    streamingPlaybackInProgress = false;
    streamingShouldShowFullControls = false;
    streamingAudioIndex = 0;

    // WS path: mark as user-stopped so ws.onclose resolves (not rejects) and
    // then tear down the AudioWorklet and AudioContext to halt playback.
    _wsUserStopped = true;
    if (_streamingWorkletNode) {
        _streamingWorkletNode.disconnect();
        _streamingWorkletNode = null;
    }
    if (_streamingAudioCtx) {
        safeCloseAudioContext(_streamingAudioCtx);
        _streamingAudioCtx = null;
    }

    // Close WebSocket if open — onclose will handle building the player from
    // whatever PCM was received so far.
    if (audiobookWs) {
        try {
            audiobookWs.send(JSON.stringify({ type: 'stop' }));
            audiobookWs.close();
        } catch (e) {}
        audiobookWs = null;
    }

    // SSE path: close the AudioContext (kills ALL scheduled audio) and reset timeline
    if (_sseAudioCtx) {
        safeCloseAudioContext(_sseAudioCtx);
        _sseAudioCtx = null;
    }
    _sseNextPlaybackTime = 0;
    _ssePrevTail = null;
    // Legacy SSE path: stop the <audio> element
    if (streamingAudioElement) {
        streamingAudioElement.pause();
        streamingAudioElement.currentTime = 0;
    }
    
    const pauseBtn = document.getElementById('audiobook-pause-btn');
    const resumeBtn = document.getElementById('audiobook-resume-btn');
    if (pauseBtn) pauseBtn.style.display = 'inline-block';
    if (resumeBtn) resumeBtn.style.display = 'none';
    
    updateStreamingStatus('Stopped');

    // Clean up progressive download link
    const progressiveLink = document.getElementById('audiobook-progressive-download');
    if (progressiveLink) {
        if (progressiveLink.dataset.blobUrl) URL.revokeObjectURL(progressiveLink.dataset.blobUrl);
        progressiveLink.remove();
    }
    _progressiveAudioChunks = [];
}

// ========== COMBINED AUDIO PLAYBACK WITH SEEKING ==========

// Combine all audio segments into a single playable audio with seek support
async function combineAudioSegments() {
    // WS path pre-builds the blob; return it immediately if already available
    if (combinedAudioUrl) {
        return combinedAudioUrl;
    }

    if (audiobookState.audioQueue.length === 0) {
        return null;
    }
    
    // Get sample rate from first segment
    const sampleRate = audiobookState.audioQueue[0].sampleRate || 24000;
    
    // Combine all PCM data
    let totalLength = 0;
    const pcmArrays = [];
    
    for (const segment of audiobookState.audioQueue) {
        const binaryString = atob(segment.audio);
        const len = binaryString.length;
        const pcmBuffer = new Uint8Array(len);
        for (let i = 0; i < len; i++) {
            pcmBuffer[i] = binaryString.charCodeAt(i) & 0xFF;
        }
        pcmArrays.push(applyEdgeFadeToPcmBytes(pcmBuffer, sampleRate));
        totalLength += len;
        
        // Track approximate duration (16-bit mono)
        const duration = len / 2 / sampleRate;
        audioSegmentDurations.push(duration);
    }
    
    // Concatenate all PCM data
    const combinedPcm = new Uint8Array(totalLength);
    let offset = 0;
    for (const pcm of pcmArrays) {
        combinedPcm.set(pcm, offset);
        offset += pcm.length;
    }
    
    // Create WAV file
    const wavBuffer = createWavBufferFromPcm(combinedPcm, sampleRate);
    combinedAudioBlob = new Blob([wavBuffer], { type: 'audio/wav' });
    combinedAudioUrl = URL.createObjectURL(combinedAudioBlob);
    
    return combinedAudioUrl;
}

// Create WAV buffer from PCM Uint8Array
function createWavBufferFromPcm(pcmData, sampleRate) {
    const numChannels = 1;
    const bitsPerSample = 16;
    const bytesPerSample = bitsPerSample / 8;
    const blockAlign = numChannels * bytesPerSample;
    const byteRate = sampleRate * blockAlign;
    const dataSize = pcmData.length;
    const bufferSize = 44 + dataSize;
    
    const buffer = new ArrayBuffer(bufferSize);
    const view = new DataView(buffer);
    
    // RIFF header
    writeStringToView(view, 0, 'RIFF');
    view.setUint32(4, 36 + dataSize, true);
    writeStringToView(view, 8, 'WAVE');
    
    // fmt chunk
    writeStringToView(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, byteRate, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, bitsPerSample, true);
    
    // data chunk
    writeStringToView(view, 36, 'data');
    view.setUint32(40, dataSize, true);
    
    // Copy PCM data
    const offset = 44;
    for (let i = 0; i < pcmData.length; i++) {
        view.setUint8(offset + i, pcmData[i]);
    }
    
    return buffer;
}

// Show full playback controls with seek bar and download
async function showFullPlaybackControls(seekToSeconds = 0, startPlaying = false) {
    if (!audiobookPlayer) return;
    
    audiobookPlayer.style.display = 'block';
    
    // Combine audio segments
    updateStreamingStatus('Preparing audio for playback...');
    const audioUrl = await combineAudioSegments();
    
    if (!audioUrl) {
        audiobookPlayer.innerHTML = '<p>Error: No audio available</p>';
        return;
    }
    
    // Calculate total duration
    const totalDuration = audioSegmentDurations.reduce((a, b) => a + b, 0);
    
    let html = '<div class="audiobook-full-player">';
    
    // Audio element (hidden, controlled by custom UI)
    html += `<audio id="audiobook-combined-audio" src="${audioUrl}" preload="metadata"></audio>`;
    
    // Playback controls row
    html += '<div class="audiobook-controls-row">';
    html += '<button id="audiobook-rewind-btn" class="btn-icon" onclick="rewindAudiobook(10)" title="Rewind 10s">⏪</button>';
    html += '<button id="audiobook-play-full-btn" class="btn-primary" onclick="playFullAudiobook()">▶ Play</button>';
    html += '<button id="audiobook-pause-full-btn" class="btn-secondary" onclick="pauseFullAudiobook()" style="display:none;">⏸ Pause</button>';
    html += '<button id="audiobook-forward-btn" class="btn-icon" onclick="forwardAudiobook(10)" title="Forward 10s">⏩</button>';
    html += '<button class="btn-secondary" onclick="stopFullAudiobook()">⏹</button>';
    html += '</div>';
    
    // Progress bar with time display
    html += '<div class="audiobook-progress-row">';
    html += '<span id="audiobook-current-time">0:00</span>';
    html += '<div class="audiobook-seek-bar" onclick="seekAudiobook(event)" id="audiobook-seek-bar">';
    html += '<div class="audiobook-seek-progress" id="audiobook-seek-progress"></div>';
    html += '<div class="audiobook-seek-handle" id="audiobook-seek-handle"></div>';
    html += '</div>';
    html += '<span id="audiobook-total-time">' + formatTime(totalDuration) + '</span>';
    html += '</div>';
    
    // Segment info
    html += '<div class="audiobook-segment-info" id="audiobook-segment-info">';
    html += '<p>Select play to start listening</p>';
    html += '</div>';
    
    // Download button
    html += '<div class="audiobook-actions-row">';
    html += '<button class="btn-primary" onclick="downloadAudiobook()">⬇ Download Audiobook</button>';
    html += '<span id="audiobook-download-status"></span>';
    html += '</div>';
    
    html += '</div>';
    
    audiobookPlayer.innerHTML = html;
    
    // Set up audio element events
    combinedAudioElement = document.getElementById('audiobook-combined-audio');
    if (combinedAudioElement) {
        combinedAudioElement.addEventListener('timeupdate', updatePlaybackProgress);
        combinedAudioElement.addEventListener('loadedmetadata', () => {
            document.getElementById('audiobook-total-time').textContent = formatTime(combinedAudioElement.duration);
            // Restore the playback position from when generation was paused/stopped
            if (seekToSeconds > 0) {
                combinedAudioElement.currentTime = Math.min(seekToSeconds, combinedAudioElement.duration);
                updatePlaybackProgress();
            }
            if (startPlaying) {
                playFullAudiobook();
            }
        });
        combinedAudioElement.addEventListener('ended', onAudiobookEnded);
        
        // Make seek bar draggable
        setupSeekBarDrag();
    }
}

// Play full combined audiobook
function playFullAudiobook() {
    if (!combinedAudioElement) return;
    
    combinedAudioElement.play();
    audiobookState.isPlaying = true;
    
    const playBtn = document.getElementById('audiobook-play-full-btn');
    const pauseBtn = document.getElementById('audiobook-pause-full-btn');
    if (playBtn) playBtn.style.display = 'none';
    if (pauseBtn) pauseBtn.style.display = 'inline-block';
}

// Pause full combined audiobook
function pauseFullAudiobook() {
    if (!combinedAudioElement) return;
    
    combinedAudioElement.pause();
    audiobookState.isPlaying = false;
    
    const playBtn = document.getElementById('audiobook-play-full-btn');
    const pauseBtn = document.getElementById('audiobook-pause-full-btn');
    if (playBtn) playBtn.style.display = 'inline-block';
    if (pauseBtn) pauseBtn.style.display = 'none';
}

// Stop full combined audiobook
function stopFullAudiobook() {
    if (!combinedAudioElement) return;
    
    combinedAudioElement.pause();
    combinedAudioElement.currentTime = 0;
    audiobookState.isPlaying = false;
    
    const playBtn = document.getElementById('audiobook-play-full-btn');
    const pauseBtn = document.getElementById('audiobook-pause-full-btn');
    if (playBtn) playBtn.style.display = 'inline-block';
    if (pauseBtn) pauseBtn.style.display = 'none';
    
    updatePlaybackProgress();
}

// Rewind audiobook by seconds
function rewindAudiobook(seconds) {
    if (!combinedAudioElement) return;
    combinedAudioElement.currentTime = Math.max(0, combinedAudioElement.currentTime - seconds);
}

// Forward audiobook by seconds
function forwardAudiobook(seconds) {
    if (!combinedAudioElement) return;
    combinedAudioElement.currentTime = Math.min(combinedAudioElement.duration, combinedAudioElement.currentTime + seconds);
}

// Seek to position from click
function seekAudiobook(event) {
    if (!combinedAudioElement) return;
    
    const seekBar = document.getElementById('audiobook-seek-bar');
    const rect = seekBar.getBoundingClientRect();
    const percent = (event.clientX - rect.left) / rect.width;
    const newTime = percent * combinedAudioElement.duration;
    
    combinedAudioElement.currentTime = Math.max(0, Math.min(combinedAudioElement.duration, newTime));
    updatePlaybackProgress();
}

// Set up seek bar dragging
function setupSeekBarDrag() {
    const seekBar = document.getElementById('audiobook-seek-bar');
    const seekHandle = document.getElementById('audiobook-seek-handle');
    let isDragging = false;
    
    if (!seekBar || !seekHandle) return;
    
    const handleDrag = (e) => {
        if (!isDragging || !combinedAudioElement) return;
        
        const rect = seekBar.getBoundingClientRect();
        let percent;
        
        if (e.type.includes('touch')) {
            percent = (e.touches[0].clientX - rect.left) / rect.width;
        } else {
            percent = (e.clientX - rect.left) / rect.width;
        }
        
        percent = Math.max(0, Math.min(1, percent));
        const newTime = percent * combinedAudioElement.duration;
        
        combinedAudioElement.currentTime = newTime;
        updatePlaybackProgress();
    };
    
    seekHandle.addEventListener('mousedown', () => { isDragging = true; });
    seekHandle.addEventListener('touchstart', () => { isDragging = true; });
    
    document.addEventListener('mousemove', handleDrag);
    document.addEventListener('touchmove', handleDrag);
    
    document.addEventListener('mouseup', () => { isDragging = false; });
    document.addEventListener('touchend', () => { isDragging = false; });
    
    // Also allow clicking directly on seek bar
    seekBar.addEventListener('click', seekAudiobook);
}

// Update progress display
function updatePlaybackProgress() {
    if (!combinedAudioElement) return;
    
    const currentTime = combinedAudioElement.currentTime;
    const duration = combinedAudioElement.duration || 1;
    const percent = (currentTime / duration) * 100;
    
    // Update time display
    const currentTimeEl = document.getElementById('audiobook-current-time');
    if (currentTimeEl) {
        currentTimeEl.textContent = formatTime(currentTime);
    }
    
    // Update progress bar
    const progressEl = document.getElementById('audiobook-seek-progress');
    if (progressEl) {
        progressEl.style.width = `${percent}%`;
    }
    
    // Update handle position
    const handleEl = document.getElementById('audiobook-seek-handle');
    if (handleEl) {
        handleEl.style.left = `${percent}%`;
    }
    
    // Update segment info based on current time
    updateSegmentInfoForTime(currentTime);
}

// Update segment info based on current playback time
function updateSegmentInfoForTime(currentTime) {
    // Calculate which segment we're in based on accumulated durations
    let accumulatedTime = 0;
    let currentSegmentIndex = 0;
    
    for (let i = 0; i < audioSegmentDurations.length; i++) {
        if (currentTime < accumulatedTime + audioSegmentDurations[i]) {
            currentSegmentIndex = i;
            break;
        }
        accumulatedTime += audioSegmentDurations[i];
        currentSegmentIndex = i + 1;
    }
    
    if (currentSegmentIndex < audiobookState.audioQueue.length) {
        const segment = audiobookState.audioQueue[currentSegmentIndex];
        const infoEl = document.getElementById('audiobook-segment-info');
        if (infoEl && segment) {
            infoEl.innerHTML = `
                <p><strong>Speaker:</strong> ${segment.speaker || 'Unknown'}</p>
                <p><strong>Voice:</strong> ${segment.voiceUsed || 'Default'}</p>
                <p><strong>Text:</strong> ${segment.text || ''}</p>
            `;
        }
    }
}

// Called when audiobook ends
function onAudiobookEnded() {
    audiobookState.isPlaying = false;
    
    const playBtn = document.getElementById('audiobook-play-full-btn');
    const pauseBtn = document.getElementById('audiobook-pause-full-btn');
    if (playBtn) playBtn.style.display = 'inline-block';
    if (pauseBtn) pauseBtn.style.display = 'none';
}

// Download audiobook as WAV file
function downloadAudiobook() {
    if (!combinedAudioBlob) {
        alert('No audio available to download');
        return;
    }
    
    const statusEl = document.getElementById('audiobook-download-status');
    if (statusEl) statusEl.textContent = 'Preparing download...';
    
    // Create download link
    const url = URL.createObjectURL(combinedAudioBlob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'audiobook.wav';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    
    // Don't revoke URL immediately to allow download to complete
    setTimeout(() => {
        URL.revokeObjectURL(url);
    }, 1000);
    
    if (statusEl) statusEl.textContent = 'Download started!';
    setTimeout(() => {
        if (statusEl) statusEl.textContent = '';
    }, 3000);
}

// Format time as M:SS
function formatTime(seconds) {
    if (!seconds || isNaN(seconds)) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Update progress bar
function updateProgress(percent, text) {
    if (audiobookProgressBar) {
        audiobookProgressBar.style.width = `${Math.max(0, percent)}%`;
    }
    if (audiobookProgressText) {
        audiobookProgressText.textContent = text;
    }
}

// Show audiobook player
function showAudiobookPlayer() {
    if (!audiobookPlayer) return;
    
    audiobookPlayer.style.display = 'block';
    
    // Create audio player controls
    let html = '<div class="audiobook-controls">';
    html += '<button id="audiobook-play-btn" class="btn-primary" onclick="playAudiobook()">▶ Play Audiobook</button>';
    html += '<button id="audiobook-pause-btn" class="btn-secondary" onclick="pauseAudiobook()" style="display:none;">⏸ Pause</button>';
    html += '<button class="btn-secondary" onclick="stopAudiobook()">⏹ Stop</button>';
    html += '<span id="audiobook-status">Ready to play</span>';
    html += '</div>';
    
    // Show segment info
    html += '<div class="audiobook-segment-info" id="audiobook-segment-info">';
    html += '<p>Click Play to start listening</p>';
    html += '</div>';
    
    audiobookPlayer.innerHTML = html;
}

// Play audiobook
let audioPlaybackIndex = 0;
let audiobookAudioElement = null;

async function playAudiobook() {
    if (audiobookState.audioQueue.length === 0) {
        alert('No audio generated yet');
        return;
    }
    
    audiobookState.isPlaying = true;
    audioPlaybackIndex = 0;
    
    const playBtn = document.getElementById('audiobook-play-btn');
    const pauseBtn = document.getElementById('audiobook-pause-btn');
    if (playBtn) playBtn.style.display = 'none';
    if (pauseBtn) pauseBtn.style.display = 'inline-block';
    
    playNextAudioSegment();
}

// Play next audio segment
async function playNextAudioSegment() {
    if (!audiobookState.isPlaying || audioPlaybackIndex >= audiobookState.audioQueue.length) {
        stopAudiobook();
        return;
    }
    
    const segment = audiobookState.audioQueue[audioPlaybackIndex];
    
    // Update status
    const statusEl = document.getElementById('audiobook-status');
    const infoEl = document.getElementById('audiobook-segment-info');
    
    if (statusEl) {
        statusEl.textContent = `Playing ${audioPlaybackIndex + 1}/${audiobookState.audioQueue.length}`;
    }
    if (infoEl) {
        infoEl.innerHTML = `
            <p><strong>Speaker:</strong> ${segment.speaker || 'Unknown'}</p>
            <p><strong>Voice:</strong> ${segment.voiceUsed || 'Default'}</p>
            <p><strong>Text:</strong> ${segment.text || ''}</p>
        `;
    }
    
    // Create audio element
    try {
        // Convert raw PCM to WAV for playback
        const wavBuffer = createWavBufferFromBase64(segment.audio, segment.sampleRate);
        const blob = new Blob([wavBuffer], { type: 'audio/wav' });
        const audioUrl = URL.createObjectURL(blob);
        
        if (audiobookAudioElement) {
            audiobookAudioElement.pause();
            URL.revokeObjectURL(audiobookAudioElement.src);
        }
        
        audiobookAudioElement = new Audio(audioUrl);
        
        audiobookAudioElement.onended = () => {
            URL.revokeObjectURL(audioUrl);
            audioPlaybackIndex++;
            if (audiobookState.isPlaying) {
                playNextAudioSegment();
            }
        };
        
        audiobookAudioElement.onerror = (e) => {
            console.error('Audio playback error:', e);
            URL.revokeObjectURL(audioUrl);
            audioPlaybackIndex++;
            if (audiobookState.isPlaying) {
                playNextAudioSegment();
            }
        };
        
        await audiobookAudioElement.play();
        
    } catch (error) {
        console.error('Error playing segment:', error);
        audioPlaybackIndex++;
        if (audiobookState.isPlaying) {
            playNextAudioSegment();
        }
    }
}

// Pause audiobook
function pauseAudiobook() {
    audiobookState.isPlaying = false;
    
    if (audiobookAudioElement) {
        audiobookAudioElement.pause();
    }
    
    const playBtn = document.getElementById('audiobook-play-btn');
    const pauseBtn = document.getElementById('audiobook-pause-btn');
    if (playBtn) playBtn.style.display = 'inline-block';
    if (pauseBtn) pauseBtn.style.display = 'none';
    
    const statusEl = document.getElementById('audiobook-status');
    if (statusEl) statusEl.textContent = 'Paused';
}

// Stop audiobook
function stopAudiobook() {
    audiobookState.isPlaying = false;
    audioPlaybackIndex = 0;
    
    if (audiobookAudioElement) {
        audiobookAudioElement.pause();
        audiobookAudioElement.currentTime = 0;
    }
    
    const playBtn = document.getElementById('audiobook-play-btn');
    const pauseBtn = document.getElementById('audiobook-pause-btn');
    if (playBtn) playBtn.style.display = 'inline-block';
    if (pauseBtn) pauseBtn.style.display = 'none';
    
    const statusEl = document.getElementById('audiobook-status');
    if (statusEl) statusEl.textContent = audiobookState.audioQueue.length > 0 ? 'Ready to play' : 'No audio';
}

// Create WAV buffer from base64 PCM data
function createWavBufferFromBase64(base64Pcm, sampleRate) {
    const binaryString = atob(base64Pcm);
    const len = binaryString.length;
    const pcmBuffer = new ArrayBuffer(len);
    const pcmView = new Uint8Array(pcmBuffer);
    for (let i = 0; i < len; i++) {
        pcmView[i] = binaryString.charCodeAt(i) & 0xFF;
    }
    const smoothedPcmView = applyEdgeFadeToPcmBytes(pcmView, sampleRate);
    
    // Create WAV container
    const numChannels = 1;
    const bitsPerSample = 16;
    const bytesPerSample = bitsPerSample / 8;
    const blockAlign = numChannels * bytesPerSample;
    const byteRate = sampleRate * blockAlign;
    const dataSize = smoothedPcmView.byteLength;
    const bufferSize = 44 + dataSize;
    
    const buffer = new ArrayBuffer(bufferSize);
    const view = new DataView(buffer);
    
    // RIFF header
    writeStringToView(view, 0, 'RIFF');
    view.setUint32(4, 36 + dataSize, true);
    writeStringToView(view, 8, 'WAVE');
    
    // fmt chunk
    writeStringToView(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, byteRate, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, bitsPerSample, true);
    
    // data chunk
    writeStringToView(view, 36, 'data');
    view.setUint32(40, dataSize, true);
    
    // Copy PCM data
    const offset = 44;
    for (let i = 0; i < smoothedPcmView.length; i++) {
        view.setUint8(offset + i, smoothedPcmView[i]);
    }
    
    return buffer;
}

function applyEdgeFadeToPcmBytes(pcmBytes, sampleRate) {
    const totalSamples = Math.floor(pcmBytes.length / 2);
    if (totalSamples < MIN_FADE_SAMPLES) return pcmBytes;

    const int16 = new Int16Array(totalSamples);
    const byteView = new DataView(pcmBytes.buffer, pcmBytes.byteOffset, pcmBytes.byteLength);
    for (let i = 0; i < totalSamples; i++) {
        int16[i] = byteView.getInt16(i * 2, true);
    }

    const fadeSamples = Math.min(
        Math.max(MIN_FADE_SAMPLES, Math.floor(sampleRate * (AUDIO_EDGE_FADE_MS / 1000))),
        Math.floor(totalSamples / MAX_FADE_DIVISOR)
    );

    for (let i = 0; i < fadeSamples; i++) {
        const gain = i / fadeSamples;
        int16[i] = Math.round(int16[i] * gain);
        int16[totalSamples - 1 - i] = Math.round(int16[totalSamples - 1 - i] * gain);
    }

    return new Uint8Array(int16.buffer);
}

function writeStringToView(view, offset, string) {
    for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
    }
}

// Export functions for global access
window.initAudiobook = initAudiobook;
window.openAudiobookModal = openAudiobookModal;
window.closeAudiobookModal = closeAudiobookModal;
window.updateVoiceMapping = updateVoiceMapping;
window.updateDefaultVoice = updateDefaultVoice;
window.playAudiobook = playAudiobook;
window.pauseAudiobook = pauseAudiobook;
window.stopAudiobook = stopAudiobook;
window.pauseStreamingAudio = pauseStreamingAudio;
window.resumeStreamingAudio = resumeStreamingAudio;
window.stopStreamingAudio = stopStreamingAudio;
window.playFullAudiobook = playFullAudiobook;
window.pauseFullAudiobook = pauseFullAudiobook;
window.stopFullAudiobook = stopFullAudiobook;
window.rewindAudiobook = rewindAudiobook;
window.forwardAudiobook = forwardAudiobook;
window.seekAudiobook = seekAudiobook;
window.downloadAudiobook = downloadAudiobook;

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAudiobook);
} else {
    initAudiobook();
}

console.log('[AUDIOBOOK] audiobook.js loaded');
