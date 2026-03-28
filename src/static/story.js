/**
 * Story Teller Feature Module
 * AI-generated multi-voice audiobook stories with structured Speaker: text format
 */

(function () {
    'use strict';

    // ---------------------------------------------------------------------------
    // State
    // ---------------------------------------------------------------------------
    let storyState = {
        storyText: '',
        segments: [],
        speakers: {},        // { name: { name, gender, segment_count, suggested_voice } }
        voiceMapping: {},    // { speakerName: voiceName }
        defaultVoices: { narrator: null, female: null, male: null },
        availableVoices: [],
        isGenerating: false,
        isGeneratingAudio: false,
        audioSegments: [],   // base64 WAV chunks as they arrive
        combinedAudioUrl: null,
        abortController: null,
    };

    // Streaming playback state – play segments as they arrive
    let _playbackCtx = null;
    let _playbackEndTime = 0;
    let _decodedBuffers = [];

    // ---------------------------------------------------------------------------
    // DOM references (populated in initStory)
    // ---------------------------------------------------------------------------
    let storyModal, storyInitialized = false;

    // ---------------------------------------------------------------------------
    // Init
    // ---------------------------------------------------------------------------
    function initStory() {
        if (storyInitialized) return;
        storyInitialized = true;
        storyModal = document.getElementById('story-modal');

        // Show/hide custom prompt when genre = "custom"
        const genreSelect = document.getElementById('story-genre');
        if (genreSelect) {
            genreSelect.addEventListener('change', function () {
                const customGroup = document.getElementById('story-custom-prompt-group');
                if (customGroup) customGroup.style.display = this.value === 'custom' ? '' : 'none';
            });
        }

        console.log('[STORY] Story Teller module initialized');
    }

    // ---------------------------------------------------------------------------
    // Open / Close
    // ---------------------------------------------------------------------------
    function openStoryModal() {
        if (!storyModal) storyModal = document.getElementById('story-modal');
        if (!storyModal) return;
        storyModal.classList.add('active');
        _resetStoryState();
        _loadAvailableVoices();
        _showSection('story-setup-section');
    }
    window.openStoryModal = openStoryModal;

    function closeStoryModal() {
        if (!storyModal) return;
        storyModal.classList.remove('active');
        _abortGeneration();
    }
    window.closeStoryModal = closeStoryModal;

    // ---------------------------------------------------------------------------
    // Reset
    // ---------------------------------------------------------------------------
    function _resetStoryState() {
        _stopStreamingPlayback();

        storyState = {
            storyText: '',
            segments: [],
            speakers: {},
            voiceMapping: {},
            defaultVoices: { narrator: null, female: null, male: null },
            availableVoices: [],
            isGenerating: false,
            isGeneratingAudio: false,
            audioSegments: [],
            combinedAudioUrl: null,
            abortController: null,
        };

        const storyTextArea = _el('story-text');
        if (storyTextArea) storyTextArea.value = '';

        _hide('story-speakers-section');
        _hide('story-generate-audio-section');
        _hide('story-progress-section');
        _hide('story-player-section');
        _show('story-setup-section');

        const progressBar = _el('story-progress-bar');
        if (progressBar) progressBar.style.width = '0%';
        const progressText = _el('story-progress-text');
        if (progressText) progressText.textContent = '';

        const genBtn = _el('story-generate-btn');
        if (genBtn) { genBtn.disabled = false; genBtn.textContent = '✨ Generate Story'; }

        const genAudioBtn = _el('story-generate-audio-btn');
        if (genAudioBtn) { genAudioBtn.disabled = false; genAudioBtn.textContent = '🎙️ Generate Audiobook'; }
    }

    // ---------------------------------------------------------------------------
    // Helpers
    // ---------------------------------------------------------------------------
    function _el(id) { return document.getElementById(id); }
    function _show(id) { const e = _el(id); if (e) e.style.display = ''; }
    function _hide(id) { const e = _el(id); if (e) e.style.display = 'none'; }
    function _showSection(id) {
        // Show specific section within the modal body without hiding everything
        const e = _el(id);
        if (e) e.style.display = '';
    }

    function _abortGeneration() {
        if (storyState.abortController) {
            storyState.abortController.abort();
            storyState.abortController = null;
        }
        storyState.isGenerating = false;
        storyState.isGeneratingAudio = false;
        _stopStreamingPlayback();
    }

    // ---------------------------------------------------------------------------
    // Load available TTS voices
    // ---------------------------------------------------------------------------
    async function _loadAvailableVoices() {
        try {
            const res = await fetch('/api/tts/speakers');
            const data = await res.json();
            storyState.availableVoices = (data.speakers || []).map(s =>
                typeof s === 'string' ? s : (s.name || s.id || String(s))
            );
        } catch (_) {
            storyState.availableVoices = [];
        }
        _renderDefaultVoiceSelects();
    }

    function _buildVoiceOptions(selected) {
        const voices = storyState.availableVoices;
        if (!voices.length) return '<option value="">No voices available</option>';
        return ['<option value="">-- select voice --</option>']
            .concat(voices.map(v =>
                `<option value="${_esc(v)}"${v === selected ? ' selected' : ''}>${_esc(v)}</option>`
            )).join('');
    }

    function _esc(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // ---------------------------------------------------------------------------
    // Generate Story (LLM)
    // ---------------------------------------------------------------------------
    async function generateStory() {
        if (storyState.isGenerating) return;

        const genre = (_el('story-genre') || {}).value || 'fantasy';
        const tone = (_el('story-tone') || {}).value || 'epic';
        const length = (_el('story-length') || {}).value || 'short';
        const customPrompt = (_el('story-custom-prompt') || {}).value || '';
        const charsRaw = (_el('story-characters') || {}).value || '';

        // Parse characters (one per line: "Name - traits" or "Name: traits" or just "Name")
        const characters = charsRaw.split('\n')
            .map(l => l.trim())
            .filter(Boolean)
            .map(l => {
                const sep = l.indexOf('-') !== -1 ? '-' : (l.indexOf(':') !== -1 ? ':' : null);
                if (sep) {
                    const idx = l.indexOf(sep);
                    return { name: l.slice(0, idx).trim(), traits: l.slice(idx + 1).trim() };
                }
                return { name: l, traits: '' };
            });

        const genBtn = _el('story-generate-btn');
        if (genBtn) { genBtn.disabled = true; genBtn.textContent = '⏳ Generating...'; }

        storyState.isGenerating = true;
        _hide('story-speakers-section');
        _hide('story-generate-audio-section');
        _hide('story-player-section');

        const statusEl = _el('story-generate-status');
        if (statusEl) { statusEl.textContent = 'Generating story with AI…'; statusEl.style.display = ''; }

        try {
            const res = await fetch('/api/story/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ genre, tone, length, custom_prompt: customPrompt, characters }),
            });
            const data = await res.json();

            if (!data.success) {
                if (statusEl) statusEl.textContent = '❌ ' + (data.error || 'Generation failed');
                return;
            }

            storyState.storyText = data.story;
            storyState.segments = data.segments;

            const textArea = _el('story-text');
            if (textArea) textArea.value = data.story;

            if (statusEl) { statusEl.textContent = '✅ Story generated! Review and edit below, then assign voices.'; }

            await _detectSpeakers(data.story);

        } catch (err) {
            if (statusEl) statusEl.textContent = '❌ Error: ' + err.message;
        } finally {
            storyState.isGenerating = false;
            if (genBtn) { genBtn.disabled = false; genBtn.textContent = '✨ Generate Story'; }
        }
    }
    window.generateStory = generateStory;

    // ---------------------------------------------------------------------------
    // Detect Speakers from text
    // ---------------------------------------------------------------------------
    async function parseStoryText() {
        const textArea = _el('story-text');
        const text = textArea ? textArea.value.trim() : '';
        if (!text) {
            alert('Please enter or generate a story first.');
            return;
        }
        storyState.storyText = text;
        await _detectSpeakers(text);
    }
    window.parseStoryText = parseStoryText;

    async function _detectSpeakers(text) {
        try {
            const res = await fetch('/api/story/parse', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text }),
            });
            const data = await res.json();
            if (!data.success) return;

            storyState.segments = data.segments;
            storyState.speakers = data.speakers || {};
            storyState.availableVoices = data.available_voices || storyState.availableVoices;

            // Pre-fill voice mapping with suggestions
            for (const [name, info] of Object.entries(storyState.speakers)) {
                if (!storyState.voiceMapping[name] && info.suggested_voice) {
                    storyState.voiceMapping[name] = info.suggested_voice;
                }
            }

            _renderSpeakersList();
            _renderDefaultVoiceSelects();
            _show('story-speakers-section');
            _show('story-generate-audio-section');

        } catch (err) {
            console.error('[STORY] Speaker detection error:', err);
        }
    }

    // ---------------------------------------------------------------------------
    // Render speakers list with voice dropdowns
    // ---------------------------------------------------------------------------
    function _renderSpeakersList() {
        const container = _el('story-speakers-list');
        if (!container) return;

        const speakers = storyState.speakers;
        if (!Object.keys(speakers).length) {
            container.innerHTML = '<p style="color:var(--text-muted)">No speakers detected. Check story format (Speaker: text).</p>';
            return;
        }

        container.innerHTML = Object.values(speakers).map(sp => {
            const currentVoice = storyState.voiceMapping[sp.name] || sp.suggested_voice || '';
            return `
<div class="story-speaker-row" data-speaker="${_esc(sp.name)}">
  <div class="story-speaker-info">
    <span class="story-speaker-name">🎙 ${_esc(sp.name)}</span>
    <span class="story-speaker-count">${sp.segment_count} line${sp.segment_count !== 1 ? 's' : ''}</span>
  </div>
  <select class="story-voice-select" onchange="setStoryVoice('${_esc(sp.name)}', this.value)">
    ${_buildVoiceOptions(currentVoice)}
  </select>
</div>`;
        }).join('');
    }

    function setStoryVoice(speaker, voice) {
        storyState.voiceMapping[speaker] = voice;
    }
    window.setStoryVoice = setStoryVoice;

    // ---------------------------------------------------------------------------
    // Default voices panel
    // ---------------------------------------------------------------------------
    function _renderDefaultVoiceSelects() {
        const roles = ['narrator', 'female', 'male'];
        for (const role of roles) {
            const sel = _el(`story-default-voice-${role}`);
            if (!sel) continue;
            sel.innerHTML = _buildVoiceOptions(storyState.defaultVoices[role] || '');
            sel.onchange = () => { storyState.defaultVoices[role] = sel.value; };
        }
    }

    // ---------------------------------------------------------------------------
    // Streaming playback – play each segment as soon as it arrives
    // ---------------------------------------------------------------------------
    function _stopStreamingPlayback() {
        if (_playbackCtx && _playbackCtx.state !== 'closed') {
            try { _playbackCtx.close(); } catch (_) { /* ignore */ }
        }
        _playbackCtx = null;
        _playbackEndTime = 0;
        _decodedBuffers = [];
    }

    async function _playSegmentImmediately(b64) {
        if (!_playbackCtx) {
            _playbackCtx = new (window.AudioContext || window.webkitAudioContext)();
            _playbackEndTime = _playbackCtx.currentTime;
        }
        try {
            const binary = atob(b64);
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
            // slice(0) creates a copy because decodeAudioData detaches the buffer
            const decoded = await _playbackCtx.decodeAudioData(bytes.buffer.slice(0));
            _decodedBuffers.push(decoded);

            const source = _playbackCtx.createBufferSource();
            source.buffer = decoded;
            source.connect(_playbackCtx.destination);
            const startAt = Math.max(_playbackCtx.currentTime, _playbackEndTime);
            source.start(startAt);
            _playbackEndTime = startAt + decoded.duration;
        } catch (e) {
            console.warn('[STORY] Failed to play segment immediately:', e);
        }
    }

    // ---------------------------------------------------------------------------
    // Generate Audiobook (TTS via SSE)
    // ---------------------------------------------------------------------------
    async function generateStoryAudiobook() {
        if (storyState.isGeneratingAudio) return;

        // Refresh segments from textarea in case user edited the story
        const textArea = _el('story-text');
        const storyText = textArea ? textArea.value.trim() : storyState.storyText;
        if (!storyText) { alert('No story text found. Please generate or paste a story.'); return; }

        // Collect latest voice mapping from selects
        document.querySelectorAll('.story-speaker-row').forEach(row => {
            const name = row.dataset.speaker;
            const sel = row.querySelector('.story-voice-select');
            if (name && sel) storyState.voiceMapping[name] = sel.value;
        });

        // Re-parse to get fresh segments
        let segments = storyState.segments;
        if (!segments.length || storyText !== storyState.storyText) {
            const lines = storyText.split('\n');
            segments = [];
            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed || !trimmed.includes(':')) continue;
                const idx = trimmed.indexOf(':');
                const speaker = trimmed.slice(0, idx).trim();
                const text = trimmed.slice(idx + 1).trim();
                if (speaker && text && speaker.length <= 50) {
                    segments.push({ speaker, text });
                }
            }
        }

        if (!segments.length) {
            alert('No parseable segments found. Ensure each line is in "Speaker: text" format.');
            return;
        }

        storyState.isGeneratingAudio = true;
        storyState.audioSegments = [];
        storyState.combinedAudioUrl = null;
        _stopStreamingPlayback();

        const genBtn = _el('story-generate-audio-btn');
        if (genBtn) { genBtn.disabled = true; genBtn.textContent = '⏳ Generating Audio...'; }

        _show('story-progress-section');
        _hide('story-player-section');

        const progressBar = _el('story-progress-bar');
        const progressText = _el('story-progress-text');
        if (progressBar) progressBar.style.width = '0%';
        if (progressText) progressText.textContent = 'Starting audio generation…';

        storyState.abortController = new AbortController();

        try {
            const res = await fetch('/api/audiobook/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                signal: storyState.abortController.signal,
                body: JSON.stringify({
                    segments,
                    voice_mapping: storyState.voiceMapping,
                    default_voices: storyState.defaultVoices,
                }),
            });

            if (!res.ok) throw new Error(`Server error ${res.status}`);

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buf = '';
            let completed = 0;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buf += decoder.decode(value, { stream: true });
                const lines = buf.split('\n');
                buf = lines.pop(); // Keep incomplete last line

                for (const line of lines) {
                    if (!line.startsWith('data:')) continue;
                    const raw = line.slice(5).trim();
                    if (!raw) continue;
                    let evt;
                    try { evt = JSON.parse(raw); } catch (_) { continue; }

                    if (evt.type === 'audio') {
                        storyState.audioSegments.push(evt.audio);
                        await _playSegmentImmediately(evt.audio);
                        completed++;
                        const pct = Math.round((completed / segments.length) * 100);
                        if (progressBar) progressBar.style.width = pct + '%';
                        if (progressText) progressText.textContent = `🔊 Playing… generated ${completed} / ${segments.length} segments`;
                    } else if (evt.type === 'done') {
                        if (progressBar) progressBar.style.width = '100%';
                        if (progressText) progressText.textContent = `Done! ${completed} segments generated.`;
                        await _buildAndPlayAudio();
                    } else if (evt.type === 'error') {
                        if (progressText) progressText.textContent = '❌ ' + (evt.error || 'TTS error');
                    }
                }
            }
        } catch (err) {
            if (err.name !== 'AbortError') {
                const progressText = _el('story-progress-text');
                if (progressText) progressText.textContent = '❌ ' + err.message;
            }
        } finally {
            storyState.isGeneratingAudio = false;
            storyState.abortController = null;
            if (genBtn) { genBtn.disabled = false; genBtn.textContent = '🎙️ Generate Audiobook'; }
        }
    }
    window.generateStoryAudiobook = generateStoryAudiobook;

    // ---------------------------------------------------------------------------
    // Build combined audio and show player
    // ---------------------------------------------------------------------------
    async function _buildAndPlayAudio() {
        // Use pre-decoded buffers from streaming playback when available,
        // falling back to decoding from base64 if needed.
        let buffers = _decodedBuffers.length ? _decodedBuffers.slice() : [];

        if (!buffers.length) {
            const segs = storyState.audioSegments;
            if (!segs.length) return;
            const tmpCtx = new (window.AudioContext || window.webkitAudioContext)();
            for (const b64 of segs) {
                try {
                    const binary = atob(b64);
                    const bytes = new Uint8Array(binary.length);
                    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
                    const decoded = await tmpCtx.decodeAudioData(bytes.buffer.slice(0));
                    buffers.push(decoded);
                } catch (_) { /* skip bad segment */ }
            }
            tmpCtx.close();
        }

        if (!buffers.length) return;

        // Merge all AudioBuffers into one
        const sampleRate = buffers[0].sampleRate;
        const channels = buffers[0].numberOfChannels;
        const totalLength = buffers.reduce((sum, b) => sum + b.length, 0);

        const mergeCtx = new (window.AudioContext || window.webkitAudioContext)();
        const merged = mergeCtx.createBuffer(channels, totalLength, sampleRate);

        let offset = 0;
        for (const buf of buffers) {
            for (let c = 0; c < channels; c++) {
                merged.getChannelData(c).set(buf.getChannelData(c), offset);
            }
            offset += buf.length;
        }

        // Encode back to WAV for the download / replay audio element
        const wavBlob = _audioBufferToWavBlob(merged);
        const url = URL.createObjectURL(wavBlob);
        storyState.combinedAudioUrl = url;

        // Show player (audio is already playing via streaming; this enables
        // replay, seeking, and download once all segments are ready)
        const audioEl = _el('story-audio');
        if (audioEl) { audioEl.src = url; audioEl.load(); }

        const dlLink = _el('story-audio-download');
        if (dlLink) { dlLink.href = url; dlLink.download = 'story_audiobook.wav'; }

        _show('story-player-section');
        mergeCtx.close();
    }

    // ---------------------------------------------------------------------------
    // WAV encoder
    // ---------------------------------------------------------------------------
    function _audioBufferToWavBlob(buffer) {
        const numChannels = buffer.numberOfChannels;
        const sampleRate = buffer.sampleRate;
        const numSamples = buffer.length;
        const byteRate = sampleRate * numChannels * 2;
        const blockAlign = numChannels * 2;
        const dataSize = numSamples * numChannels * 2;
        const ab = new ArrayBuffer(44 + dataSize);
        const view = new DataView(ab);

        function writeStr(off, str) { for (let i = 0; i < str.length; i++) view.setUint8(off + i, str.charCodeAt(i)); }
        writeStr(0, 'RIFF');
        view.setUint32(4, 36 + dataSize, true);
        writeStr(8, 'WAVE');
        writeStr(12, 'fmt ');
        view.setUint32(16, 16, true);
        view.setUint16(20, 1, true);
        view.setUint16(22, numChannels, true);
        view.setUint32(24, sampleRate, true);
        view.setUint32(28, byteRate, true);
        view.setUint16(32, blockAlign, true);
        view.setUint16(34, 16, true);
        writeStr(36, 'data');
        view.setUint32(40, dataSize, true);

        // Interleave channels
        let off = 44;
        for (let i = 0; i < numSamples; i++) {
            for (let c = 0; c < numChannels; c++) {
                const s = Math.max(-1, Math.min(1, buffer.getChannelData(c)[i]));
                view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
                off += 2;
            }
        }
        return new Blob([ab], { type: 'audio/wav' });
    }

    // ---------------------------------------------------------------------------
    // DOM ready bootstrap
    // ---------------------------------------------------------------------------
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initStory);
    } else {
        initStory();
    }

})();
