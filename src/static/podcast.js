/**
 * AI Podcasting Feature Module
 * Multi-voice streaming generation, playback, editing & export
 */

(function() {
    'use strict';

// Podcast state
let podcastState = {
    episode: null,
    episodeId: null,
    voiceProfiles: {},
    isGenerating: false,
    generationProgress: {
        phase: '',
        percent: 0,
        message: ''
    },
    isPlaying: false,
    isPaused: false,
    currentTime: 0,
    duration: 0,
    playbackSpeed: 1.0,
    audioQueue: [],
    audioSegments: [],
    combinedAudioBlob: null,
    combinedAudioUrl: null,
    audioElement: null,
    transcript: [],
    currentSegmentIndex: -1,
    activeTab: 'studio',
    showTranscript: true,
    bookmarks: [],
    abortController: null
};

// DOM elements
let podcastModal, podcastProgress, podcastProgressBar, podcastProgressText;
let podcastPlayer, podcastAudio;
let podcastInitialized = false;

// Constants
const PODCAST_FORMATS = {
    interview: { name: 'Interview', description: 'Q&A style', defaultSpeakers: ['Host', 'Guest'] },
    debate: { name: 'Debate', description: 'Opposing viewpoints', defaultSpeakers: ['Moderator', 'Proponent', 'Opponent'] },
    educational: { name: 'Educational', description: 'Teaching a topic', defaultSpeakers: ['Narrator', 'Expert'] },
    storytelling: { name: 'Storytelling', description: 'Narrative content', defaultSpeakers: ['Narrator', 'Character'] },
    conversation: { name: 'Casual Conversation', description: 'Free-flowing discussion', defaultSpeakers: ['Speaker 1', 'Speaker 2'] }
};

const EPISODE_LENGTHS = {
    short: { minutes: 5, name: 'Short (~5 min)' },
    medium: { minutes: 15, name: 'Medium (~15 min)' },
    long: { minutes: 30, name: 'Long (~30 min)' },
    extended: { minutes: 60, name: 'Extended (~60 min)' }
};

// Initialize podcast feature
function initPodcast() {
    if (podcastInitialized) return;
    podcastInitialized = true;
    
    console.log('[PODCAST] Initializing podcast module...');
    
    // Get DOM elements
    podcastModal = document.getElementById('podcast-modal');
    podcastProgress = document.getElementById('podcast-progress');
    podcastProgressBar = document.getElementById('podcast-progress-bar');
    podcastProgressText = document.getElementById('podcast-progress-text');
    podcastPlayer = document.getElementById('podcast-player');
    podcastAudio = document.getElementById('podcast-audio');
    
    // Set up event listeners
    const podcastBtn = document.getElementById('podcastBtn');
    if (podcastBtn) {
        podcastBtn.addEventListener('click', openPodcastModal);
    }
    
    // Load voice profiles
    loadVoiceProfiles();
    
    console.log('[PODCAST] Podcast module initialized');
}

// Open podcast modal
function openPodcastModal() {
    if (podcastModal) {
        podcastModal.classList.add('active');
        // Reset form to show setup sections with empty fields
        initPodcastForm();
        loadEpisodesList();
        renderVoiceProfilesList();
    }
}

// Close podcast modal
function closePodcastModal() {
    // Stop streaming playback (closes AudioContext, kills all scheduled audio)
    stopPodcastStreaming();

    // Pause HTML <audio> element if present
    if (podcastState.audioElement) {
        podcastState.audioElement.pause();
        podcastState.audioElement = null;
    }

    // Abort any ongoing generation
    if (podcastState.abortController) {
        podcastState.abortController.abort();
        podcastState.abortController = null;
    }

    // Revoke blob URL to free memory
    if (podcastState.combinedAudioUrl) {
        URL.revokeObjectURL(podcastState.combinedAudioUrl);
        podcastState.combinedAudioUrl = null;
    }

    // Reset all playback/generation state so reopening is a fresh instance
    podcastState.episode = null;
    podcastState.episodeId = null;
    podcastState.isGenerating = false;
    podcastState.isPlaying = false;
    podcastState.isPaused = false;
    podcastState.currentTime = 0;
    podcastState.duration = 0;
    podcastState.audioQueue = [];
    podcastState.audioSegments = [];
    podcastState.combinedAudioBlob = null;
    podcastState.transcript = [];
    podcastState.currentSegmentIndex = -1;
    podcastState.bookmarks = [];

    if (podcastModal) {
        podcastModal.classList.remove('active');
    }
}

// Load voice profiles
async function loadVoiceProfiles() {
    try {
        const response = await fetch('/api/podcast/voice-profiles');
        const data = await response.json();
        if (data.success) {
            podcastState.voiceProfiles = {};
            data.profiles.forEach(profile => {
                podcastState.voiceProfiles[profile.id] = profile;
            });
        }
    } catch (error) {
        console.error('[PODCAST] Error loading voice profiles:', error);
    }
}

// Render voice profiles list
function renderVoiceProfilesList() {
    const container = document.getElementById('podcast-voice-profiles-list');
    if (!container) return;
    
    const profiles = Object.values(podcastState.voiceProfiles);
    
    if (profiles.length === 0) {
        container.innerHTML = '<p>No voice profiles. Create one to get started!</p>';
        return;
    }
    
    let html = '';
    profiles.forEach(profile => {
        html += `
            <div class="voice-profile-card" data-profile-id="${profile.id}">
                <span class="voice-profile-name">${profile.name}</span>
                <span class="voice-profile-voice">${profile.voice_id || 'Default'}</span>
                ${profile.llm_prompt ? '<span class="voice-profile-prompt">📝</span>' : ''}
            </div>
        `;
    });
    container.innerHTML = html;
}

// Generate podcast outline
async function generatePodcastOutline() {
    // Get form values
    let topic = document.getElementById('podcast-topic')?.value 
        || document.getElementById('topic')?.value
        || document.querySelector('.podcast-topic-input')?.value;
    
    if (!topic) {
        alert('Please enter a topic for the podcast');
        return;
    }
    
    // Show progress
    showPodcastProgress();
    updatePodcastProgress(0, 'Generating outline...');
    
    try {
        const response = await fetch('/api/podcast/generate-outline', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ topic })
        });
        
        const data = await response.json();
        
        if (data.success && data.outline) {
            // Fill in the talking points
            const pointsTextarea = document.getElementById('podcast-points');
            if (pointsTextarea) {
                pointsTextarea.value = data.outline.join('\n');
            }
            updatePodcastProgress(100, 'Outline generated!');
        } else {
            updatePodcastProgress(-1, 'Error generating outline');
        }
    } catch (error) {
        console.error('[PODCAST] Outline generation error:', error);
        updatePodcastProgress(-1, `Error: ${error.message}`);
    }
}

// Generate podcast episode
async function generatePodcast() {
    // Get form values - try multiple possible element IDs
    let topic = document.getElementById('podcast-topic')?.value 
        || document.getElementById('topic')?.value
        || document.querySelector('.podcast-topic-input')?.value;
    
    // If no topic found, search modal for any text input with value
    if (!topic) {
        const modalBody = document.querySelector('#podcast-modal .modal-body');
        if (modalBody) {
            const inputs = modalBody.querySelectorAll('input[type="text"], textarea');
            for (const input of inputs) {
                if (input.value && input.value.length > 5) {
                    topic = input.value;
                    break;
                }
            }
        }
    }
    
    if (!topic) {
        alert('Please enter a topic for the podcast');
        return;
    }
    
    // Get speakers from modal
    const speakers = [];
    const speakerRows = document.querySelectorAll('#podcast-speakers-list .podcast-speaker-row');
    speakerRows.forEach(row => {
        const nameInput = row.querySelector('.podcast-speaker-name');
        const voiceSelect = row.querySelector('.podcast-speaker-voice');
        const promptInput = row.querySelector('.podcast-speaker-prompt');
        if (nameInput && nameInput.value) {
            speakers.push({
                name: nameInput.value,
                voice_id: voiceSelect?.value || null,
                llm_prompt: promptInput?.value || '',  // Include LLM prompt
                profile_id: null
            });
        }
    });
    
    // If no speakers found, use defaults
    if (speakers.length === 0) {
        speakers.push({ name: 'Host', voice_id: null, profile_id: null });
        speakers.push({ name: 'Guest', voice_id: null, profile_id: null });
    }
    
    // Get format and length
    const format = document.getElementById('podcast-format')?.value || 'interview';
    const length = document.getElementById('podcast-length')?.value || 'medium';
    
    // Initialize episode state
    podcastState.episode = {
        id: 'ep_' + Date.now().toString(36),
        title: topic.substring(0, 50),
        topic,
        format,
        length,
        speakers,
        transcript: [],
        created_at: new Date().toISOString(),
        status: 'generating'
    };
    
    podcastState.isGenerating = true;
    podcastState.isPlaying = true;
    podcastState.audioQueue = [];
    podcastState.audioSegments = [];
    
    // Show progress and player immediately - like audiobook does
    showPodcastProgress();
    showPodcastStreamingPlayer();
    
    updatePodcastProgress(0, 'Starting generation...');
    
    try {
        const response = await fetch('/api/podcast/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(podcastState.episode)
        });
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            
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
                            handlePodcastEvent(data);
                        } catch (e) {
                            console.error('[PODCAST] Parse error:', e);
                        }
                    }
                }
            }
        }
        
    } catch (error) {
        if (error.name !== 'AbortError') {
            console.error('[PODCAST] Generation error:', error);
            updatePodcastProgress(-1, `Error: ${error.message}`);
        }
    } finally {
        podcastState.isGenerating = false;
    }
}

// Handle generation events
function handlePodcastEvent(data) {
    switch (data.type) {
        case 'phase':
            updatePodcastProgress(data.percent || 0, data.message);
            break;
            
        case 'audio':
            podcastState.audioQueue.push({
                audio: data.audio,
                sample_rate: data.sample_rate,
                segment_index: data.segment_index,
                speaker: data.speaker,
                text: data.text,
                voice_used: data.voice_used
            });
            
            // Build transcript from audio events
            if (podcastState.episode && data.speaker && data.text) {
                podcastState.episode.transcript.push({
                    speaker: data.speaker,
                    text: data.text
                });
            }
            
            // Update progress using server-provided percent
            const percent = typeof data.percent === 'number' ? Math.round(data.percent) : 0;
            const segInfo = data.total_segments ? ` (${data.segment_index + 1}/${data.total_segments})` : '';
            updatePodcastProgress(percent, `Generating audio${segInfo}...`);
            
            // Start streaming playback if first chunk - like audiobook!
            if (podcastState.audioQueue.length === 1 && !streamingPlaybackActive) {
                startPodcastStreamingPlayback();
            }
            break;
            
        case 'transcript':
            podcastState.episode.transcript = data.transcript;
            updatePodcastTranscriptDisplay();
            break;
            
        case 'done':
            updatePodcastProgress(100, 'Generation complete!');
            finalizePodcastEpisode(data);
            break;
            
        case 'error':
            updatePodcastProgress(-1, `Error: ${data.error}`);
            break;
    }
}

// Update progress display
function updatePodcastProgress(percent, text) {
    if (podcastProgressBar) {
        podcastProgressBar.style.width = `${Math.max(0, percent)}%`;
    }
    if (podcastProgressText) {
        podcastProgressText.textContent = text;
    }
    if (podcastProgress) {
        podcastProgress.style.display = 'block';
    }
}

// Show progress section
function showPodcastProgress() {
    if (podcastProgress) {
        // Hide other sections
        const setupSection = document.querySelector('#podcast-modal .podcast-setup-section');
        const speakersSection = document.querySelector('#podcast-modal .podcast-speakers-section');
        const actionsSection = document.querySelector('#podcast-modal .podcast-actions');
        
        if (setupSection) setupSection.style.display = 'none';
        if (speakersSection) speakersSection.style.display = 'none';
        if (actionsSection) actionsSection.style.display = 'none';
        
        podcastProgress.style.display = 'block';
    }
}

// Streaming playback state
let streamingPlaybackActive = false;
let streamingPlaybackIndex = 0;
let streamingAudioElement = null;
// Reusable AudioContext + timeline scheduling for streaming playback
let _podcastAudioCtx = null;
let _podcastNextPlaybackTime = 0;
const PODCAST_TARGET_SAMPLE_RATE = 24000;
const PODCAST_INITIAL_BUFFER_SEC = 0.25;
// Crossfade state: previous chunk tail for equal-power overlap
let _podcastPrevTail = null;
const PODCAST_CROSSFADE_SAMPLES = 512; // ~21ms @ 24kHz

// Show streaming player - like audiobook does
function showPodcastStreamingPlayer() {
    if (!podcastPlayer) return;
    
    podcastPlayer.style.display = 'block';
    
    let html = '<div class="podcast-controls">';
    html += '<button id="podcast-pause-btn" class="btn-secondary" onclick="pausePodcastStreaming()">⏸ Pause</button>';
    html += '<button id="podcast-resume-btn" class="btn-primary" onclick="resumePodcastStreaming()" style="display:none;">▶ Resume</button>';
    html += '<button class="btn-secondary" onclick="stopPodcastStreaming()">⏹ Stop</button>';
    html += '<span id="podcast-status">Generating and streaming...</span>';
    html += '</div>';
    
    html += '<div class="podcast-segment-info" id="podcast-segment-info">';
    html += '<p>Preparing first audio segment...</p>';
    html += '</div>';
    
    podcastPlayer.innerHTML = html;
    
    streamingPlaybackActive = false;
    streamingPlaybackIndex = 0;
}

// Show streaming player when generation is complete - keeps controls available to stop auto-play
function showPodcastStreamingPlayerComplete() {
    if (!podcastPlayer) return;
    
    podcastPlayer.style.display = 'block';
    
    // Determine if we should show pause or resume based on current state
    const isCurrentlyPlaying = podcastState.isPlaying;
    
    let html = '<div class="podcast-controls">';
    html += '<button id="podcast-pause-btn" class="btn-secondary" onclick="pausePodcastStreaming()" ' + (isCurrentlyPlaying ? '' : 'style="display:none;"') + '>⏸ Pause</button>';
    html += '<button id="podcast-resume-btn" class="btn-primary" onclick="resumePodcastStreaming()" ' + (isCurrentlyPlaying ? 'style="display:none;"' : '') + '>▶ Resume</button>';
    html += '<button class="btn-secondary" onclick="stopPodcastStreaming()">⏹ Stop</button>';
    html += '<button class="btn-primary" onclick="showPodcastFullPlayer()">📼 Full Player</button>';
    html += '<span id="podcast-status">Generation complete!</span>';
    html += '</div>';
    
    html += '<div class="podcast-segment-info" id="podcast-segment-info">';
    html += '<p>Audio generation complete. Use Stop to end playback or switch to Full Player for seeking.</p>';
    html += '</div>';
    
    podcastPlayer.innerHTML = html;
}

// Start streaming playback - like audiobook!
function startPodcastStreamingPlayback() {
    if (streamingPlaybackActive) return;
    streamingPlaybackActive = true;
    streamingPlaybackIndex = 0;
    podcastState.isPlaying = true;
    
    playNextPodcastChunk();
}

// Play next audio chunk - schedules chunks on timeline as they arrive
async function playNextPodcastChunk() {
    while (podcastState.isPlaying) {
        if (streamingPlaybackIndex >= podcastState.audioQueue.length) {
            if (!podcastState.isGenerating) {
                updatePodcastStatus('Playback complete!');
                break;
            }
            await new Promise(resolve => setTimeout(resolve, 100));
            continue;
        }
        
        const chunk = podcastState.audioQueue[streamingPlaybackIndex];
        // Schedule on timeline (fire-and-forget, no await)
        playPodcastChunk(chunk);
        streamingPlaybackIndex++;
    }
    
    streamingPlaybackActive = false;
}

// Schedule a single audio chunk on the global timeline (fire-and-forget)
function playPodcastChunk(chunk) {
    try {
        const sampleRate = chunk.sample_rate;

        // Decode base64 PCM to raw bytes
        const binaryString = atob(chunk.audio);
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
            _podcastPrevTail = float32.length > 0 ? new Float32Array(float32) : null;
            // fall through to schedule the tiny chunk as-is
        } else {
            // Equal-power crossfade: blend start of this chunk with tail of previous chunk,
            // then trim the overlapped region to prevent energy duplication
            if (_podcastPrevTail && float32.length > 0) {
                const overlap = Math.min(_podcastPrevTail.length, float32.length, PODCAST_CROSSFADE_SAMPLES);
                if (overlap > 0) {
                    for (let i = 0; i < overlap; i++) {
                        const t = i / overlap;
                        const fadeOut = Math.cos(t * Math.PI * 0.5);
                        const fadeIn  = Math.sin(t * Math.PI * 0.5);
                        float32[i] = _podcastPrevTail[i] * fadeOut + float32[i] * fadeIn;
                    }
                    // Trim overlapped portion to prevent energy duplication
                    float32 = float32.slice(overlap);
                }
            }

            // Store tail safely for next crossfade (after trimming)
            const tailLen = Math.min(PODCAST_CROSSFADE_SAMPLES, float32.length);
            _podcastPrevTail = tailLen > 0 ? float32.slice(float32.length - tailLen) : null;
        }

        if (sampleRate !== PODCAST_TARGET_SAMPLE_RATE) {
            console.warn('[PODCAST] Sample rate mismatch:', sampleRate,
                         'expected:', PODCAST_TARGET_SAMPLE_RATE);
        }

        // Lazily create a shared AudioContext (never recreate mid-stream)
        if (!_podcastAudioCtx || _podcastAudioCtx.state === 'closed') {
            _podcastAudioCtx = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: PODCAST_TARGET_SAMPLE_RATE,
                latencyHint: 'interactive'
            });
            _podcastNextPlaybackTime = _podcastAudioCtx.currentTime + PODCAST_INITIAL_BUFFER_SEC;
        }
        if (_podcastAudioCtx.state === 'suspended') {
            _podcastAudioCtx.resume();
        }

        const audioBuffer = _podcastAudioCtx.createBuffer(1, float32.length, PODCAST_TARGET_SAMPLE_RATE);
        audioBuffer.getChannelData(0).set(float32);

        const source = _podcastAudioCtx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(_podcastAudioCtx.destination);

        // Underrun protection
        const now = _podcastAudioCtx.currentTime;
        if (_podcastNextPlaybackTime < now) {
            _podcastNextPlaybackTime = now + 0.05;
        }

        // Schedule on the global timeline (gapless)
        source.start(_podcastNextPlaybackTime);
        _podcastNextPlaybackTime += audioBuffer.duration;

        // Update status
        updatePodcastStatus(`Playing segment ${streamingPlaybackIndex + 1}`);
        updatePodcastSegmentInfo(chunk);

    } catch (error) {
        console.error('[PODCAST] Error scheduling chunk:', error);
    }
}

// Update podcast status
function updatePodcastStatus(text) {
    const statusEl = document.getElementById('podcast-status');
    if (statusEl) statusEl.textContent = text;
}

// Update segment info
function updatePodcastSegmentInfo(segment) {
    const infoEl = document.getElementById('podcast-segment-info');
    if (infoEl) {
        infoEl.innerHTML = `
            <p><strong>Speaker:</strong> ${segment.speaker || 'Unknown'}</p>
            <p><strong>Text:</strong> ${segment.text || ''}</p>
        `;
    }
}

// Update transcript display
function updatePodcastTranscriptDisplay() {
    const content = document.getElementById('podcast-transcript-content');
    if (content && podcastState.episode?.transcript) {
        content.innerHTML = podcastState.episode.transcript.map(seg => 
            `<div class="transcript-segment"><strong>${seg.speaker}:</strong> ${seg.text}</div>`
        ).join('');
    }
}

// Pause streaming
function pausePodcastStreaming() {
    podcastState.isPlaying = false;
    
    if (_podcastAudioCtx && _podcastAudioCtx.state === 'running') {
        _podcastAudioCtx.suspend().catch(e =>
            console.warn('[PODCAST] AudioContext suspend failed:', e));
    }
    if (streamingAudioElement) {
        streamingAudioElement.pause();
    }
    
    const pauseBtn = document.getElementById('podcast-pause-btn');
    const resumeBtn = document.getElementById('podcast-resume-btn');
    if (pauseBtn) pauseBtn.style.display = 'none';
    if (resumeBtn) resumeBtn.style.display = 'inline-block';
    
    updatePodcastStatus('Paused');
}

// Resume streaming
function resumePodcastStreaming() {
    podcastState.isPlaying = true;
    
    if (_podcastAudioCtx && _podcastAudioCtx.state === 'suspended') {
        _podcastAudioCtx.resume().catch(e =>
            console.warn('[PODCAST] AudioContext resume failed:', e));
    }
    
    const pauseBtn = document.getElementById('podcast-pause-btn');
    const resumeBtn = document.getElementById('podcast-resume-btn');
    if (pauseBtn) pauseBtn.style.display = 'inline-block';
    if (resumeBtn) resumeBtn.style.display = 'none';
    
    if (!streamingPlaybackActive) {
        startPodcastStreamingPlayback();
    }
}

// Stop streaming
function stopPodcastStreaming() {
    podcastState.isPlaying = false;
    streamingPlaybackActive = false;
    streamingPlaybackIndex = 0;
    
    // Close AudioContext (kills ALL scheduled audio) and reset timeline
    if (_podcastAudioCtx) {
        if (_podcastAudioCtx.state !== 'closed') {
            _podcastAudioCtx.close().catch(() => {});
        }
        _podcastAudioCtx = null;
    }
    _podcastNextPlaybackTime = 0;
    _podcastPrevTail = null;
    if (streamingAudioElement) {
        streamingAudioElement.pause();
    }
    
    const pauseBtn = document.getElementById('podcast-pause-btn');
    const resumeBtn = document.getElementById('podcast-resume-btn');
    if (pauseBtn) pauseBtn.style.display = 'inline-block';
    if (resumeBtn) resumeBtn.style.display = 'none';
    
    updatePodcastStatus('Stopped');
}

// Finalize episode
async function finalizePodcastEpisode(data) {
    updatePodcastProgress(100, 'Episode complete!');
    
    podcastState.episode.status = 'complete';
    podcastState.episode.duration = data.duration || 0;
    
    // Combine audio for seeking
    await combinePodcastAudio();
    
    // Save episode
    await savePodcastEpisode();
    
    // Refresh episodes list so new episode appears in library
    loadEpisodesList();
    
    // Show streaming player with stop button still available - user can stop playback
    // The full player will be available but we keep streaming controls until user stops or plays full
    showPodcastStreamingPlayerComplete();
}

// Combine audio segments
async function combinePodcastAudio() {
    if (podcastState.audioQueue.length === 0) return;
    
    const sampleRate = podcastState.audioQueue[0].sample_rate || 24000;
    
    let totalLength = 0;
    const pcmArrays = [];
    
    for (const chunk of podcastState.audioQueue) {
        const binaryString = atob(chunk.audio);
        const len = binaryString.length;
        const pcmBuffer = new Uint8Array(len);
        for (let i = 0; i < len; i++) {
            pcmBuffer[i] = binaryString.charCodeAt(i) & 0xFF;
        }
        pcmArrays.push(pcmBuffer);
        totalLength += len;
    }
    
    const combinedPcm = new Uint8Array(totalLength);
    let offset = 0;
    for (const pcm of pcmArrays) {
        combinedPcm.set(pcm, offset);
        offset += pcm.length;
    }
    
    const wavBuffer = createWavBufferFromPcm(combinedPcm, sampleRate);
    podcastState.combinedAudioBlob = new Blob([wavBuffer], { type: 'audio/wav' });
    podcastState.combinedAudioUrl = URL.createObjectURL(podcastState.combinedAudioBlob);
    
    podcastState.duration = totalLength / 2 / sampleRate;
}

// Show full player with controls
function showPodcastFullPlayer() {
    if (!podcastPlayer) return;
    
    podcastPlayer.style.display = 'block';
    
    const episode = podcastState.episode;
    
    let html = '<div class="podcast-full-player">';
    
    // Audio element - only set src if URL is valid
    if (podcastState.combinedAudioUrl) {
        html += `<audio id="podcast-combined-audio" src="${podcastState.combinedAudioUrl}" preload="metadata"></audio>`;
    } else {
        html += `<audio id="podcast-combined-audio" preload="metadata"></audio>`;
    }
    
    // Title
    html += `<h3>${episode.title}</h3>`;
    html += `<p>${formatTime(podcastState.duration)} • ${episode.speakers.length} speakers</p>`;
    
    // Controls - larger, more professional
    html += '<div class="podcast-controls-row">';
    html += '<button class="btn-icon" onclick="rewindPodcast(10)">⏪</button>';
    html += '<button id="podcast-play-full-btn" class="btn-primary" onclick="playPodcastFull()">▶ Play</button>';
    html += '<button id="podcast-pause-full-btn" class="btn-secondary" onclick="pausePodcastFull()" style="display:none;">⏸</button>';
    html += '<button class="btn-icon" onclick="forwardPodcast(10)">⏩</button>';
    html += '</div>';
    
    // Progress - styled seek bar
    html += '<div class="podcast-progress-row">';
    html += '<span id="podcast-current-time">0:00</span>';
    html += '<input type="range" id="podcast-seek" min="0" max="' + Math.floor(podcastState.duration) + '" value="0" step="0.1" oninput="seekPodcast(this.value)">';
    html += '<span id="podcast-total-time">' + formatTime(podcastState.duration) + '</span>';
    html += '</div>';
    
    // Transcript - shorter panel with scroll
    html += '<div class="podcast-transcript">';
    html += '<h4>Transcript</h4>';
    html += '<div id="podcast-transcript-content">';
    if (podcastState.episode.transcript) {
        html += podcastState.episode.transcript.map(seg => 
            `<div class="transcript-segment"><strong>${seg.speaker}:</strong><p>${seg.text}</p></div>`
        ).join('');
    }
    html += '</div>';
    html += '</div>';
    
    // Actions
    html += '<div class="podcast-actions">';
    html += '<button class="btn-primary" onclick="downloadPodcast()">⬇ Download</button>';
    html += '<button class="btn-secondary" onclick="initPodcastForm()">+ New Episode</button>';
    html += '</div>';
    
    html += '</div>';
    
    podcastPlayer.innerHTML = html;
    
    // Set up audio element
    podcastState.audioElement = document.getElementById('podcast-combined-audio');
    if (podcastState.audioElement) {
        podcastState.audioElement.addEventListener('timeupdate', updatePodcastPlaybackTime);
        podcastState.audioElement.addEventListener('ended', onPodcastEnded);
    }
}

// Play full combined audio
function playPodcastFull() {
    if (!podcastState.audioElement) return;
    if (!podcastState.combinedAudioUrl) {
        console.warn('[PODCAST] No audio URL available for playback');
        alert('Podcast audio not generated. Check TTS service.');
        return;
    }
    
    podcastState.audioElement.play().catch(err => {
        console.error('[PODCAST] Playback error:', err);
    });
    podcastState.isPlaying = true;
    
    const playBtn = document.getElementById('podcast-play-full-btn');
    const pauseBtn = document.getElementById('podcast-pause-full-btn');
    if (playBtn) playBtn.style.display = 'none';
    if (pauseBtn) pauseBtn.style.display = 'inline-block';
}

// Pause full audio
function pausePodcastFull() {
    if (!podcastState.audioElement) return;
    
    podcastState.audioElement.pause();
    podcastState.isPlaying = false;
    
    const playBtn = document.getElementById('podcast-play-full-btn');
    const pauseBtn = document.getElementById('podcast-pause-full-btn');
    if (playBtn) playBtn.style.display = 'inline-block';
    if (pauseBtn) pauseBtn.style.display = 'none';
}

// Seek
function seekPodcast(time) {
    if (!podcastState.audioElement) return;
    podcastState.audioElement.currentTime = time;
}

// Rewind/Forward
function rewindPodcast(seconds) {
    if (!podcastState.audioElement) return;
    podcastState.audioElement.currentTime = Math.max(0, podcastState.audioElement.currentTime - seconds);
}

function forwardPodcast(seconds) {
    if (!podcastState.audioElement) return;
    podcastState.audioElement.currentTime = Math.min(podcastState.duration, podcastState.audioElement.currentTime + seconds);
}

// Update playback time
function updatePodcastPlaybackTime() {
    if (!podcastState.audioElement) return;
    
    const currentTime = podcastState.audioElement.currentTime;
    
    const currentEl = document.getElementById('podcast-current-time');
    const seekEl = document.getElementById('podcast-seek');
    
    if (currentEl) currentEl.textContent = formatTime(currentTime);
    if (seekEl) seekEl.value = currentTime;
}

// On ended
function onPodcastEnded() {
    podcastState.isPlaying = false;
    
    const playBtn = document.getElementById('podcast-play-full-btn');
    const pauseBtn = document.getElementById('podcast-pause-full-btn');
    if (playBtn) playBtn.style.display = 'inline-block';
    if (pauseBtn) pauseBtn.style.display = 'none';
}

// Download podcast
function downloadPodcast() {
    if (!podcastState.combinedAudioBlob) {
        alert('No audio available');
        return;
    }
    
    const url = URL.createObjectURL(podcastState.combinedAudioBlob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${podcastState.episode.title.replace(/[^a-z0-9]/gi, '_')}.wav`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Load episodes list
async function loadEpisodesList() {
    const container = document.getElementById('podcast-episodes-list');
    if (!container) return;
    
    try {
        const response = await fetch('/api/podcast/episodes');
        const data = await response.json();
        
        if (data.success) {
            const episodes = data.episodes || [];
            if (episodes.length === 0) {
                container.innerHTML = '<p class="no-episodes">No episodes yet. Create your first episode!</p>';
            } else {
                let html = '';
                episodes.forEach(episode => {
                    const date = episode.created_at ? new Date(episode.created_at).toLocaleDateString() : 'Unknown date';
                    html += `
                        <div class="podcast-episode-item" onclick="loadEpisode('${episode.id}')">
                            <div class="podcast-episode-info">
                                <span class="podcast-episode-title">${episode.title || 'Untitled Episode'}</span>
                                <span class="podcast-episode-meta">
                                    <span>${episode.format || 'conversation'}</span>
                                    <span>${date}</span>
                                </span>
                            </div>
                            <div class="podcast-episode-actions">
                                <button class="play-episode-btn" onclick="event.stopPropagation(); playEpisode('${episode.id}')" title="Play">
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                                        <path d="M8 5V19L19 12L8 5Z" stroke="currentColor" stroke-width="2"/>
                                    </svg>
                                </button>
                                <button class="delete-episode-btn" onclick="event.stopPropagation(); deleteEpisode('${episode.id}')" title="Delete">
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                                        <path d="M3 6H5H21" stroke="currentColor" stroke-width="2"/>
                                        <path d="M19 6V20C19 21 18 22 17 22H7C6 22 5 21 5 20V6" stroke="currentColor" stroke-width="2"/>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    `;
                });
                container.innerHTML = html;
            }
        } else {
            container.innerHTML = '<p class="no-episodes">Error loading episodes.</p>';
        }
    } catch (error) {
        console.error('[PODCAST] Error loading episodes:', error);
        container.innerHTML = '<p class="no-episodes">Error loading episodes.</p>';
    }
}

// Load episode for editing
function loadEpisode(episodeId) {
    console.log('[PODCAST] Load episode:', episodeId);
    // Could implement episode editing in the future
}

// Play episode
async function playEpisode(episodeId) {
    console.log('[PODCAST] Play episode:', episodeId);
    
    // Open the podcast modal first
    openPodcastModal();
    
    // Hide setup sections and show player area
    const setupSection = document.querySelector('#podcast-modal .podcast-setup-section');
    const speakersSection = document.querySelector('#podcast-modal .podcast-speakers-section');
    const actionsSection = document.querySelector('#podcast-modal .podcast-actions');
    const progressSection = document.getElementById('podcast-progress');
    
    if (setupSection) setupSection.style.display = 'none';
    if (speakersSection) speakersSection.style.display = 'none';
    if (actionsSection) actionsSection.style.display = 'none';
    if (progressSection) progressSection.style.display = 'none';
    
    try {
        // Fetch episode details from API
        const response = await fetch(`/api/podcast/episodes/${episodeId}`);
        const data = await response.json();
        
        if (data.success && data.episode) {
            const episode = data.episode;
            
            // Store episode in state
            podcastState.episode = episode;
            
            // Check for audio_url first (newer episodes with combined audio)
            if (episode.audio_url) {
                podcastState.combinedAudioUrl = episode.audio_url;
                podcastState.duration = episode.duration || 0;
                
                // Show the full player with the audio
                showPodcastFullPlayer();
                
                // Auto-play
                setTimeout(() => {
                    if (podcastState.audioElement) {
                        podcastState.audioElement.play().catch(err => {
                            console.error('[PODCAST] Auto-play error:', err);
                        });
                    }
                }, 100);
            }
            // Fallback: try audio_segments (older episodes)
            else if (episode.audio_segments && episode.audio_segments.length > 0) {
                // Reconstruct audio from segments
                podcastState.audioQueue = episode.audio_segments.map(seg => ({
                    audio: seg.audio,
                    sample_rate: seg.sample_rate || 24000,
                    segment_index: seg.segment_index,
                    speaker: seg.speaker,
                    text: seg.text,
                    voice_used: seg.voice_used
                }));
                
                // Combine audio
                await combinePodcastAudio();
                
                // Show the full player with the audio
                showPodcastFullPlayer();
                
                // Auto-play
                setTimeout(() => {
                    if (podcastState.audioElement) {
                        podcastState.audioElement.play().catch(err => {
                            console.error('[PODCAST] Auto-play error:', err);
                        });
                    }
                }, 100);
            } else {
                alert('No audio available for this episode');
            }
        } else {
            alert('Episode not found');
        }
    } catch (error) {
        console.error('[PODCAST] Error playing episode:', error);
        alert('Error loading episode');
    }
}

// Delete episode
async function deleteEpisode(episodeId) {
    if (!confirm('Are you sure you want to delete this episode?')) return;
    
    try {
        const response = await fetch(`/api/podcast/episodes/${episodeId}`, {
            method: 'DELETE'
        });
        const data = await response.json();
        
        if (data.success) {
            loadEpisodesList(); // Refresh the list
        } else {
            alert('Error deleting episode');
        }
    } catch (error) {
        console.error('[PODCAST] Error deleting episode:', error);
        alert('Error deleting episode');
    }
}

// Save episode
async function savePodcastEpisode() {
    try {
        await fetch(`/api/podcast/episodes/${podcastState.episode.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(podcastState.episode)
        });
    } catch (error) {
        console.error('[PODCAST] Error saving episode:', error);
    }
}

// Init podcast form
function initPodcastForm() {
    // Reset form visibility
    const setupSection = document.querySelector('#podcast-modal .podcast-setup-section');
    const speakersSection = document.querySelector('#podcast-modal .podcast-speakers-section');
    const actionsSection = document.querySelector('#podcast-modal .podcast-actions');
    const progressSection = document.getElementById('podcast-progress');
    const playerSection = document.getElementById('podcast-player');
    
    if (setupSection) setupSection.style.display = 'block';
    if (speakersSection) speakersSection.style.display = 'block';
    if (actionsSection) actionsSection.style.display = 'flex';
    if (progressSection) progressSection.style.display = 'none';
    if (playerSection) playerSection.style.display = 'none';
    
    // Clear all form fields
    const topicInput = document.getElementById('podcast-topic');
    if (topicInput) topicInput.value = '';
    
    const titleInput = document.getElementById('podcast-title');
    if (titleInput) titleInput.value = '';
    
    const formatSelect = document.getElementById('podcast-format');
    if (formatSelect) formatSelect.value = 'conversation';
    
    const lengthSelect = document.getElementById('podcast-length');
    if (lengthSelect) lengthSelect.value = 'medium';
    
    const pointsTextarea = document.getElementById('podcast-points');
    if (pointsTextarea) pointsTextarea.value = '';
    
    // Clear speaker rows and reload them
    const speakersContainer = document.getElementById('podcast-speakers-list');
    if (speakersContainer) {
        speakersContainer.innerHTML = '';
    }
    
    // Stop any ongoing streaming playback and close AudioContext
    stopPodcastStreaming();

    // Pause and release HTML audio element
    if (podcastState.audioElement) {
        podcastState.audioElement.pause();
        podcastState.audioElement = null;
    }

    // Revoke old blob URL to free memory
    if (podcastState.combinedAudioUrl) {
        URL.revokeObjectURL(podcastState.combinedAudioUrl);
        podcastState.combinedAudioUrl = null;
    }

    // Reset audio state
    podcastState.episode = null;
    podcastState.episodeId = null;
    podcastState.audioQueue = [];
    podcastState.audioSegments = [];
    podcastState.combinedAudioBlob = null;
    podcastState.isPlaying = false;
    podcastState.isPaused = false;
    podcastState.isGenerating = false;
    podcastState.currentTime = 0;
    podcastState.duration = 0;
    podcastState.transcript = [];
    podcastState.currentSegmentIndex = -1;
    podcastState.bookmarks = [];
    
    // Load voices for speakers
    loadVoicesForPodcastSpeakers();
}

// Load voices for speakers
async function loadVoicesForPodcastSpeakers() {
    const speakersContainer = document.getElementById('podcast-speakers-list');
    if (!speakersContainer) return;
    
    try {
        const response = await fetch('/api/tts/speakers');
        const data = await response.json();
        
        let voicesHtml = '<option value="">Select Voice...</option>';
        if (data.success && data.speakers) {
            data.speakers.forEach(speaker => {
                const id = speaker.id || speaker.name;
                const name = speaker.name || speaker.id;
                voicesHtml += `<option value="${id}">${name}</option>`;
            });
        }
        
        // Check if speakers exist
        if (speakersContainer.children.length === 0) {
            // Add default speakers with LLM prompt field
            speakersContainer.innerHTML = `
                <div class="podcast-speaker-row">
                    <div class="speaker-inputs">
                        <input type="text" class="podcast-speaker-name" value="Host" placeholder="Speaker Name">
                        <select class="podcast-speaker-voice">${voicesHtml}</select>
                        <input type="text" class="podcast-speaker-prompt" placeholder="LLM Prompt (optional): e.g., 'Speaks in an enthusiastic, energetic manner'">
                    </div>
                </div>
                <div class="podcast-speaker-row">
                    <div class="speaker-inputs">
                        <input type="text" class="podcast-speaker-name" value="Guest" placeholder="Speaker Name">
                        <select class="podcast-speaker-voice">${voicesHtml}</select>
                        <input type="text" class="podcast-speaker-prompt" placeholder="LLM Prompt (optional): e.g., 'Provides expert technical insights'">
                    </div>
                </div>
            `;
        } else {
            // Update existing selects
            speakersContainer.querySelectorAll('.podcast-speaker-voice').forEach(select => {
                select.innerHTML = voicesHtml;
            });
        }
    } catch (error) {
        console.error('[PODCAST] Error loading voices:', error);
        // Still show default speakers even if voice API is unavailable
        if (speakersContainer && speakersContainer.children.length === 0) {
            speakersContainer.innerHTML = `
                <div class="podcast-speaker-row">
                    <div class="speaker-inputs">
                        <input type="text" class="podcast-speaker-name" value="Host" placeholder="Speaker Name">
                        <select class="podcast-speaker-voice"><option value="">Select Voice...</option></select>
                        <input type="text" class="podcast-speaker-prompt" placeholder="LLM Prompt (optional): e.g., 'Speaks in an enthusiastic, energetic manner'">
                    </div>
                </div>
                <div class="podcast-speaker-row">
                    <div class="speaker-inputs">
                        <input type="text" class="podcast-speaker-name" value="Guest" placeholder="Speaker Name">
                        <select class="podcast-speaker-voice"><option value="">Select Voice...</option></select>
                        <input type="text" class="podcast-speaker-prompt" placeholder="LLM Prompt (optional): e.g., 'Provides expert technical insights'">
                    </div>
                </div>
            `;
        }
    }
}

// Add speaker
function addPodcastSpeaker() {
    console.log('[PODCAST] addPodcastSpeaker called');
    const container = document.getElementById('podcast-speakers-list');
    if (!container) {
        console.error('[PODCAST] Speaker container not found!');
        return;
    }
    
    console.log('[PODCAST] Fetching speakers...');
    fetch('/api/tts/speakers')
        .then(r => {
            console.log('[PODCAST] Speakers response:', r.status);
            return r.json();
        })
        .then(data => {
            console.log('[PODCAST] Speakers data:', data);
            let voicesHtml = '<option value="">Select Voice...</option>';
            if (data.success && data.speakers) {
                data.speakers.forEach(speaker => {
                    const id = speaker.id || speaker.name;
                    const name = speaker.name || speaker.id;
                    voicesHtml += `<option value="${id}">${name}</option>`;
                });
            }
            
            const row = document.createElement('div');
            row.className = 'podcast-speaker-row';
            row.innerHTML = `
                <div class="speaker-inputs">
                    <input type="text" class="podcast-speaker-name" placeholder="Speaker Name">
                    <select class="podcast-speaker-voice">${voicesHtml}</select>
                    <input type="text" class="podcast-speaker-prompt" placeholder="LLM Prompt (optional)">
                    <button type="button" class="remove-speaker-btn" onclick="this.closest('.podcast-speaker-row').remove()">×</button>
                </div>
            `;
            container.appendChild(row);
            console.log('[PODCAST] Speaker row added');
        })
        .catch(err => {
            console.error('[PODCAST] Error adding speaker:', err);
        });
}

// Format time
function formatTime(seconds) {
    if (!seconds || isNaN(seconds)) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Create WAV buffer from base64
function createWavBufferFromBase64(base64Pcm, sampleRate) {
    const binaryString = atob(base64Pcm);
    const len = binaryString.length;
    const pcmBuffer = new ArrayBuffer(len);
    const pcmView = new Uint8Array(pcmBuffer);
    for (let i = 0; i < len; i++) {
        pcmView[i] = binaryString.charCodeAt(i) & 0xFF;
    }
    return createWavBufferFromPcm(new Uint8Array(pcmBuffer), sampleRate);
}

// Create WAV buffer from PCM
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
    
    writeStringToView(view, 0, 'RIFF');
    view.setUint32(4, 36 + dataSize, true);
    writeStringToView(view, 8, 'WAVE');
    writeStringToView(view, 12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, byteRate, true);
    view.setUint16(32, blockAlign, true);
    view.setUint16(34, bitsPerSample, true);
    writeStringToView(view, 36, 'data');
    view.setUint32(40, dataSize, true);
    
    const offset = 44;
    for (let i = 0; i < pcmData.length; i++) {
        view.setUint8(offset + i, pcmData[i]);
    }
    
    return buffer;
}

function writeStringToView(view, offset, string) {
    for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
    }
}

// Export functions
window.initPodcast = initPodcast;
window.openPodcastModal = openPodcastModal;
window.closePodcastModal = closePodcastModal;
window.generatePodcastOutline = generatePodcastOutline;
window.generatePodcast = generatePodcast;
window.addPodcastSpeaker = addPodcastSpeaker;
window.initPodcastForm = initPodcastForm;
window.pausePodcastStreaming = pausePodcastStreaming;
window.resumePodcastStreaming = resumePodcastStreaming;
window.stopPodcastStreaming = stopPodcastStreaming;
window.showPodcastFullPlayer = showPodcastFullPlayer;
window.playPodcastFull = playPodcastFull;
window.pausePodcastFull = pausePodcastFull;
window.seekPodcast = seekPodcast;
window.rewindPodcast = rewindPodcast;
window.forwardPodcast = forwardPodcast;
window.downloadPodcast = downloadPodcast;
window.loadEpisode = loadEpisode;
window.playEpisode = playEpisode;
window.deleteEpisode = deleteEpisode;

// Auto-initialize
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPodcast);
} else {
    initPodcast();
}

console.log('[PODCAST] podcast.js loaded');

})();
