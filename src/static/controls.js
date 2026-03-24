/**
 * LM Studio Chatbot - Controls Module
 * XTTS, STT, and Voice Clone control panels
 */

// ============================================================
// XTTS CONTROL PANEL
// ============================================================

const xttsStatusContainer = document.getElementById('xttsStatusContainer');
const xttsStatusDot = document.getElementById('xttsStatusDot');
const xttsStatusText = document.getElementById('xttsStatusText');
const xttsControlModal = document.getElementById('xttsControlModal');
const closeXttSControl = document.getElementById('closeXttSControl');
const xttsModalStatusDot = document.getElementById('xttsModalStatusDot');
const xttsModalStatusText = document.getElementById('xttsModalStatusText');
const xttsStartBtn = document.getElementById('xttsStartBtn');
const xttsStopBtn = document.getElementById('xttsStopBtn');
const xttsRestartBtn = document.getElementById('xttsRestartBtn');
const xttsLogsContent = document.getElementById('xttsLogsContent');
const xttsRefreshLogsBtn = document.getElementById('xttsRefreshLogs');

let xttsStatusInterval = null;

function setupXTTSControl() {
    if (!xttsStatusContainer) return;
    
    xttsStatusContainer.addEventListener('click', () => {
        xttsControlModal.classList.add('active');
        refreshXTTSLogs();
    });
    
    if (closeXttSControl) {
        closeXttSControl.addEventListener('click', () => { xttsControlModal.classList.remove('active'); });
    }
    
    xttsControlModal.addEventListener('click', (e) => {
        if (e.target === xttsControlModal) {
            xttsControlModal.classList.remove('active');
        }
    });
    
    xttsStartBtn.addEventListener('click', startXTTS);
    xttsStopBtn.addEventListener('click', stopXTTS);
    xttsRestartBtn.addEventListener('click', restartXTTS);
    xttsRefreshLogsBtn.addEventListener('click', refreshXTTSLogs);
    
    // Initial status check with more retries for Docker startup
    // Give services time to initialize (they start sequentially)
    setTimeout(() => checkXTTSStatus(), 3000);
    xttsStatusInterval = setInterval(checkXTTSStatus, 5000);
}

async function checkXTTSStatus() {
    const maxRetries = 3;
    const retryDelay = 1500;
    
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
            // For FasterQwen3TTS, check if the provider is available via the API
            const response = await fetch('/api/providers/status');
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.tts && data.tts.available) {
                    updateXTTSStatus(true, 'TTS: Running (FasterQwen3TTS)');
                    return;
                }
            }
        } catch (e) {
            // Provider not responding, continue to retry
        }
        
        if (attempt < maxRetries) {
            await new Promise(resolve => setTimeout(resolve, retryDelay));
        }
    }
    
    // Also try the Flask API endpoint as fallback
    try {
        const statusResponse = await fetch('/api/services/status', { timeout: 5000 });
        const statusData = await statusResponse.json();
        if (statusData.success && statusData.tts && statusData.tts.running) {
            updateXTTSStatus(true, 'TTS: Running');
            return;
        }
    } catch (e) {
        // Fallback also failed
    }
    
    updateXTTSStatus(false, 'TTS: Stopped');
}

function updateXTTSStatus(running, text) {
    xttsStatusDot.className = running ? 'status-dot connected' : 'status-dot disconnected';
    xttsStatusText.textContent = text;
    
    if (xttsModalStatusDot) {
        xttsModalStatusDot.className = running ? 'status-dot large connected' : 'status-dot large disconnected';
    }
    if (xttsModalStatusText) {
        xttsModalStatusText.textContent = running ? 'Running' : 'Stopped';
    }
    
    if (xttsStartBtn) xttsStartBtn.disabled = running;
    if (xttsStopBtn) xttsStopBtn.disabled = !running;
    if (xttsRestartBtn) xttsRestartBtn.disabled = !running;
}

async function startXTTS() {
    xttsStartBtn.disabled = true;
    xttsStartBtn.textContent = 'Starting...';
    
    try {
        const response = await fetch('/api/services/xtts/start', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            setTimeout(() => {
                checkXTTSStatus();
                refreshXTTSLogs();
            }, 3000);
        }
    } catch (e) {
        console.error('Error starting XTTS:', e);
    }
    
    xttsStartBtn.textContent = 'Start';
    xttsStartBtn.disabled = false;
}

async function stopXTTS() {
    xttsStopBtn.disabled = true;
    xttsStopBtn.textContent = 'Stopping...';
    
    try {
        const response = await fetch('/api/services/xtts/stop', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            setTimeout(() => {
                checkXTTSStatus();
                refreshXTTSLogs();
            }, 2000);
        }
    } catch (e) {
        console.error('Error stopping XTTS:', e);
    }
    
    xttsStopBtn.textContent = 'Stop';
    xttsStopBtn.disabled = false;
}

async function restartXTTS() {
    xttsRestartBtn.disabled = true;
    xttsRestartBtn.textContent = 'Restarting...';
    
    try {
        const response = await fetch('/api/services/xtts/restart', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            setTimeout(() => {
                checkXTTSStatus();
                refreshXTTSLogs();
            }, 5000);
        }
    } catch (e) {
        console.error('Error restarting XTTS:', e);
    }
    
    xttsRestartBtn.textContent = 'Restart';
    xttsRestartBtn.disabled = false;
}

async function refreshXTTSLogs() {
    if (!xttsLogsContent) return;
    try {
        const response = await fetch('/api/services/xtts/logs');
        const data = await response.json();
        
        if (data.success && data.logs) {
            if (data.logs.length === 0) {
                xttsLogsContent.textContent = 'No logs available. Make sure TTS service is running.';
            } else {
                xttsLogsContent.textContent = data.logs.join('\n');
            }
        } else {
            xttsLogsContent.textContent = 'Unable to fetch logs. Service may not be running.';
        }
    } catch (e) {
        xttsLogsContent.textContent = 'Error connecting to log service: ' + e.message;
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupXTTSControl);
} else {
    setupXTTSControl();
}

// ============================================================
// STT CONTROL PANEL
// ============================================================

const sttStatusContainer = document.getElementById('sttStatusContainer');
const sttStatusDot = document.getElementById('sttStatusDot');
const sttStatusText = document.getElementById('sttStatusText');
const sttControlModal = document.getElementById('sttControlModal');
const closeSttControl = document.getElementById('closeSttControl');
const sttModalStatusDot = document.getElementById('sttModalStatusDot');
const sttModalStatusText = document.getElementById('sttModalStatusText');
const sttStartBtn = document.getElementById('sttStartBtn');
const sttStopBtn = document.getElementById('sttStopBtn');
const sttRestartBtn = document.getElementById('sttRestartBtn');
const sttLogsContent = document.getElementById('sttLogsContent');
const sttRefreshLogsBtn = document.getElementById('sttRefreshLogs');

function setupSTTControl() {
    if (!sttStatusContainer) return;
    
    sttStatusContainer.addEventListener('click', () => {
        sttControlModal.classList.add('active');
        refreshSTTLogs();
    });
    
    if (closeSttControl) {
        closeSttControl.addEventListener('click', () => { sttControlModal.classList.remove('active'); });
    }
    
    sttControlModal.addEventListener('click', (e) => {
        if (e.target === sttControlModal) {
            sttControlModal.classList.remove('active');
        }
    });
    
    sttStartBtn.addEventListener('click', startSTT);
    sttStopBtn.addEventListener('click', stopSTT);
    sttRestartBtn.addEventListener('click', restartSTT);
    sttRefreshLogsBtn.addEventListener('click', refreshSTTLogs);
    
    // Initial status check with delay for Docker startup
    setTimeout(() => checkSTTStatus(), 3000);
    setInterval(checkSTTStatus, 5000);
}

async function checkSTTStatus() {
    // First try direct health check for faster response
    try {
        const healthResponse = await fetch('http://localhost:8000/health', { timeout: 3000 });
        if (healthResponse.status === 200) {
            updateSTTStatus(true, 'STT: Running');
            return;
        }
    } catch (e) {
        // STT not responding, continue to fallback
    }
    
    // Fallback to Flask API endpoint
    try {
        const response = await fetch('/api/services/status', { timeout: 5000 });
        const data = await response.json();
        
        if (data.success && data.stt && data.stt.running) {
            updateSTTStatus(true, 'STT: Running');
        } else {
            updateSTTStatus(false, 'STT: Stopped');
        }
    } catch (e) {
        updateSTTStatus(false, 'STT: Stopped');
    }
}

function updateSTTStatus(running, text) {
    sttStatusDot.className = running ? 'status-dot connected' : 'status-dot disconnected';
    sttStatusText.textContent = text;
    
    if (sttModalStatusDot) {
        sttModalStatusDot.className = running ? 'status-dot large connected' : 'status-dot large disconnected';
    }
    if (sttModalStatusText) {
        sttModalStatusText.textContent = running ? 'Running' : 'Stopped';
    }
    
    if (sttStartBtn) sttStartBtn.disabled = running;
    if (sttStopBtn) sttStopBtn.disabled = !running;
    if (sttRestartBtn) sttRestartBtn.disabled = !running;
}

async function startSTT() {
    sttStartBtn.disabled = true;
    sttStartBtn.textContent = 'Starting...';
    
    try {
        const response = await fetch('/api/services/stt/start', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            setTimeout(() => {
                checkSTTStatus();
                refreshSTTLogs();
            }, 3000);
        }
    } catch (e) {
        console.error('Error starting STT:', e);
    }
    
    sttStartBtn.textContent = 'Start';
    sttStartBtn.disabled = false;
}

async function stopSTT() {
    sttStopBtn.disabled = true;
    sttStopBtn.textContent = 'Stopping...';
    
    try {
        const response = await fetch('/api/services/stt/stop', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            setTimeout(() => {
                checkSTTStatus();
                refreshSTTLogs();
            }, 2000);
        }
    } catch (e) {
        console.error('Error stopping STT:', e);
    }
    
    sttStopBtn.textContent = 'Stop';
    sttStopBtn.disabled = false;
}

async function restartSTT() {
    sttRestartBtn.disabled = true;
    sttRestartBtn.textContent = 'Restarting...';
    
    try {
        const response = await fetch('/api/services/stt/restart', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            setTimeout(() => {
                checkSTTStatus();
                refreshSTTLogs();
            }, 5000);
        }
    } catch (e) {
        console.error('Error restarting STT:', e);
    }
    
    sttRestartBtn.textContent = 'Restart';
    sttRestartBtn.disabled = false;
}

async function refreshSTTLogs() {
    if (!sttLogsContent) return;
    try {
        const response = await fetch('/api/services/stt/logs');
        const data = await response.json();
        
        if (data.success && data.logs) {
            if (data.logs.length === 0) {
                sttLogsContent.textContent = 'No logs available. Make sure STT service is running.';
            } else {
                sttLogsContent.textContent = data.logs.join('\n');
            }
        } else {
            sttLogsContent.textContent = 'Unable to fetch logs. Service may not be running.';
        }
    } catch (e) {
        sttLogsContent.textContent = 'Error connecting to log service: ' + e.message;
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupSTTControl);
} else {
    setupSTTControl();
}

// ============================================================
// VOICE CLONING
// ============================================================

// Support both sidebar button formats (expanded and collapsed)
// Get all possible voice clone buttons (they all should work)
const voiceCloneBtns = [
    document.getElementById('voiceCloneBtn'),
    document.getElementById('voiceCloneBtnOption'),
    document.getElementById('voiceCloneBtnCollapsed')
].filter(btn => btn !== null);

const voiceCloneModal = document.getElementById('voiceCloneModal');
const closeVoiceClone = document.getElementById('closeVoiceClone');
const voiceNameInput = document.getElementById('voiceName');
const cloneLanguageSelect = document.getElementById('cloneLanguage');
const recordVoiceBtn = document.getElementById('recordVoiceBtn');
const recordingStatus = document.getElementById('recordingStatus');
const recordedPreview = document.getElementById('recordedPreview');
const saveVoiceBtn = document.getElementById('saveVoiceBtn');

// Upload tab elements
const recordTabBtn = document.getElementById('recordTabBtn');
const uploadTabBtn = document.getElementById('uploadTabBtn');
const recordTab = document.getElementById('recordTab');
const uploadTab = document.getElementById('uploadTab');
const uploadDropZone = document.getElementById('uploadDropZone');
const audioFileInput = document.getElementById('audioFileInput');
const browseAudioBtn = document.getElementById('browseAudioBtn');
const uploadedFileInfo = document.getElementById('uploadedFileInfo');
const uploadedFileName = document.getElementById('uploadedFileName');
const removeUploadedFile = document.getElementById('removeUploadedFile');

let voiceCloneMediaRecorder = null;
let voiceCloneAudioChunks = [];
let isVoiceCloning = false;
let uploadedAudioFile = null;  // For file upload
let voiceCloneSource = 'record';  // 'record' or 'upload'

// Tab switching
function showVoiceTab(tab) {
    voiceCloneSource = tab;
    
    // Update tab buttons
    recordTabBtn.classList.toggle('active', tab === 'record');
    uploadTabBtn.classList.toggle('active', tab === 'upload');
    
    // Update tab content
    recordTab.classList.toggle('active', tab === 'record');
    uploadTab.classList.toggle('active', tab === 'upload');
    
    // Reset state when switching tabs
    if (tab === 'record') {
        uploadedAudioFile = null;
        uploadedFileInfo.style.display = 'none';
        uploadDropZone.style.display = 'flex';
    } else {
        voiceCloneAudioChunks = [];
        recordedPreview.style.display = 'none';
    }
    
    updateSaveButton();
}

// Make showVoiceTab globally accessible for onclick
window.showVoiceTab = showVoiceTab;

function updateSaveButton() {
    const hasName = voiceNameInput.value.trim();
    const hasAudio = (voiceCloneSource === 'record' && voiceCloneAudioChunks.length > 0) ||
                     (voiceCloneSource === 'upload' && uploadedAudioFile);
    saveVoiceBtn.disabled = !hasName || !hasAudio;
}

function setupVoiceClone() {
    if (voiceCloneBtns.length === 0) return;
    
    // Add click handler to ALL voice clone buttons
    voiceCloneBtns.forEach(btn => {
        btn.addEventListener('click', () => { 
            voiceCloneModal.classList.add('active');
            // Reset to record tab
            showVoiceTab('record');
            // Load saved voices
            loadSavedVoices();
        });
    });
    
    closeVoiceClone.addEventListener('click', () => { voiceCloneModal.classList.remove('active'); });
    
    voiceCloneModal.addEventListener('click', (e) => {
        if (e.target === voiceCloneModal) {
            voiceCloneModal.classList.remove('active');
        }
    });
    
    voiceNameInput.addEventListener('input', updateSaveButton);
    
    // Recording handlers
    recordVoiceBtn.addEventListener('mousedown', startVoiceCloneRecording);
    recordVoiceBtn.addEventListener('mouseup', stopVoiceCloneRecording);
    recordVoiceBtn.addEventListener('mouseleave', stopVoiceCloneRecording);
    
    recordVoiceBtn.addEventListener('touchstart', (e) => { e.preventDefault(); startVoiceCloneRecording(); });
    recordVoiceBtn.addEventListener('touchend', (e) => { e.preventDefault(); stopVoiceCloneRecording(); });
    
    // Upload handlers
    if (browseAudioBtn) {
        browseAudioBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            audioFileInput.click();
        });
    }
    
    if (audioFileInput) {
        audioFileInput.addEventListener('change', handleAudioFileSelect);
    }
    
    // Drag and drop
    if (uploadDropZone) {
        uploadDropZone.addEventListener('click', () => audioFileInput.click());
        
        uploadDropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadDropZone.classList.add('dragover');
        });
        
        uploadDropZone.addEventListener('dragleave', (e) => {
            e.preventDefault();
            uploadDropZone.classList.remove('dragover');
        });
        
        uploadDropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadDropZone.classList.remove('dragover');
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                handleAudioFile(files[0]);
            }
        });
    }
    
    // Remove uploaded file
    if (removeUploadedFile) {
        removeUploadedFile.addEventListener('click', (e) => {
            e.stopPropagation();
            clearUploadedFile();
        });
    }
    
    saveVoiceBtn.addEventListener('click', saveClonedVoice);
}

function handleAudioFileSelect(e) {
    const file = e.target.files[0];
    if (file) {
        handleAudioFile(file);
    }
}

function handleAudioFile(file) {
    // Check file type
    const validTypes = ['audio/wav', 'audio/mpeg', 'audio/mp3', 'audio/ogg', 'audio/flac', 'audio/x-m4a', 'audio/webm', 'audio/aac'];
    const extension = file.name.split('.').pop().toLowerCase();
    const validExtensions = ['wav', 'mp3', 'ogg', 'flac', 'm4a', 'webm', 'aac'];
    
    if (!validTypes.includes(file.type) && !validExtensions.includes(extension)) {
        alert('Please select a valid audio file (WAV, MP3, OGG, FLAC, M4A, WebM, or AAC)');
        return;
    }
    
    // Check file size (max 50MB)
    if (file.size > 50 * 1024 * 1024) {
        alert('File is too large. Maximum size is 50MB.');
        return;
    }
    
    uploadedAudioFile = file;
    
    // Show file info
    uploadedFileName.textContent = file.name;
    uploadDropZone.style.display = 'none';
    uploadedFileInfo.style.display = 'block';
    
    // Show audio preview
    const audioUrl = URL.createObjectURL(file);
    recordedPreview.src = audioUrl;
    recordedPreview.style.display = 'block';
    
    updateSaveButton();
}

function clearUploadedFile() {
    uploadedAudioFile = null;
    uploadedFileInfo.style.display = 'none';
    uploadDropZone.style.display = 'flex';
    recordedPreview.style.display = 'none';
    recordedPreview.src = '';
    audioFileInput.value = '';
    updateSaveButton();
}

async function startVoiceCloneRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        recordingStatus.textContent = 'Recording not supported in this browser';
        return;
    }
    
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        
        voiceCloneAudioChunks = [];
        voiceCloneMediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
        
        voiceCloneMediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                voiceCloneAudioChunks.push(event.data);
            }
        };
        
        voiceCloneMediaRecorder.onstop = () => {
            stream.getTracks().forEach(track => track.stop());
            showVoicePreview();
        };
        
        voiceCloneMediaRecorder.start(100);
        
        isVoiceCloning = true;
        recordVoiceBtn.classList.add('recording');
        recordingStatus.textContent = 'Recording...';
        recordingStatus.className = 'recording-status recording';
    } catch (e) {
        console.error('Failed to start recording:', e);
        recordingStatus.textContent = 'Failed to access microphone';
    }
}

function stopVoiceCloneRecording() {
    if (!isVoiceCloning) return;
    
    isVoiceCloning = false;
    recordVoiceBtn.classList.remove('recording');
    
    if (voiceCloneMediaRecorder && voiceCloneMediaRecorder.state === 'recording') {
        voiceCloneMediaRecorder.stop();
    }
    
    recordingStatus.textContent = 'Recording stopped';
    recordingStatus.className = 'recording-status';
}

function showVoicePreview() {
    if (voiceCloneAudioChunks.length === 0) return;
    
    const audioBlob = new Blob(voiceCloneAudioChunks, { type: 'audio/webm' });
    const audioUrl = URL.createObjectURL(audioBlob);
    
    recordedPreview.src = audioUrl;
    recordedPreview.style.display = 'block';
    recordingStatus.textContent = 'Recording complete - ready to save';
    saveVoiceBtn.disabled = !voiceNameInput.value.trim();
}

async function saveClonedVoice() {
    const voiceName = voiceNameInput.value.trim();
    const language = cloneLanguageSelect.value;
    const genderSelect = document.getElementById('voiceGender');
    const gender = genderSelect ? genderSelect.value : 'neutral';
    
    if (!voiceName) {
        alert('Please enter a voice name');
        return;
    }
    
    // Check if we have audio from either source
    let audioBlob = null;
    let fileName = 'recording.webm';
    
    if (voiceCloneSource === 'upload') {
        if (!uploadedAudioFile) {
            alert('Please select an audio file');
            return;
        }
        audioBlob = uploadedAudioFile;
        fileName = uploadedAudioFile.name;
    } else {
        if (voiceCloneAudioChunks.length === 0) {
            alert('Please record your voice first');
            return;
        }
        audioBlob = new Blob(voiceCloneAudioChunks, { type: 'audio/webm' });
    }
    
    saveVoiceBtn.disabled = true;
    saveVoiceBtn.textContent = 'Saving...';
    
    try {
        const formData = new FormData();
        formData.append('file', audioBlob, fileName);
        formData.append('voice_id', voiceName);
        formData.append('ref_text', `Reference voice for ${voiceName}`);
        formData.append('gender', gender);
        
        const response = await fetch('/api/voice_clone', { method: 'POST', body: formData });
        const data = await response.json();
        
        if (data.success) {
            alert(`Voice "${voiceName}" created successfully!`);
            voiceCloneModal.classList.remove('active');
            voiceNameInput.value = '';
            recordedPreview.style.display = 'none';
            recordedPreview.src = '';
            voiceCloneAudioChunks = [];
            uploadedAudioFile = null;
            
            // Refresh speakers and select the new voice
            if (typeof loadTTSSpeakers === 'function') {
                await loadTTSSpeakers();
                // Select the newly created voice
                const ttsSpeaker = document.getElementById('ttsSpeaker');
                if (ttsSpeaker) {
                    ttsSpeaker.value = voiceName;
                    localStorage.setItem('selectedSpeaker', voiceName);
                }
            }
            
            // Refresh the saved voices list
            loadSavedVoices();
        } else {
            alert('Error: ' + (data.error || 'Failed to create voice'));
        }
    } catch (e) {
        alert('Error saving voice: ' + e.message);
    } finally {
        saveVoiceBtn.disabled = false;
        saveVoiceBtn.textContent = 'Save Voice';
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupVoiceClone);
} else {
    setupVoiceClone();
}

// ============================================================
// MANAGE SAVED VOICES
// ============================================================

// Load saved voices when modal opens
function loadSavedVoices() {
    console.log('[VOICE CLONES] loadSavedVoices called');
    
    // Get the element fresh each time to avoid stale references
    const savedVoicesListEl = document.getElementById('savedVoicesList');
    
    if (!savedVoicesListEl) {
        console.error('[VOICE CLONES] savedVoicesList element not found!');
        return;
    }
    
    console.log('[VOICE CLONES] Fetching from /api/voice_clones...');
    
    fetch('/api/voice_clones')
        .then(response => {
            console.log('[VOICE CLONES] Response status:', response.status);
            return response.json();
        })
        .then(data => {
            console.log('[VOICE CLONES] Response data:', data);
            if (data.success && data.voices && data.voices.length > 0) {
                console.log('[VOICE CLONES] Rendering', data.voices.length, 'voices');
                renderSavedVoices(data.voices, savedVoicesListEl);
            } else {
                console.log('[VOICE CLONES] No voices found');
                savedVoicesListEl.innerHTML = '<p class="no-voices">No saved voices yet. Create your first voice clone above!</p>';
            }
        })
        .catch(e => {
            console.error('[VOICE CLONES] Error loading voices:', e);
            savedVoicesListEl.innerHTML = '<p class="no-voices">Error loading voices. Please check if the server is running.</p>';
        });
}

function renderSavedVoices(voices, containerEl) {
    // Get existing voice profiles (personalities)
    const profiles = typeof getVoiceProfiles === 'function' ? getVoiceProfiles() : {};
    
    containerEl.innerHTML = voices.map(voice => {
        const profile = profiles[voice.id];
        const hasPersonality = profile && profile.personality;
        const personalityPreview = hasPersonality 
            ? (profile.personality.length > 50 ? profile.personality.substring(0, 50) + '...' : profile.personality)
            : '';
        const genderLabel = voice.gender || 'neutral';
        
        return `
        <div class="saved-voice-item" data-voice-id="${voice.id}">
            <div class="saved-voice-info">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                    <path d="M12 1C10.9 1 10 1.9 10 3V12C10 13.1 10.9 14 12 14C13.1 14 14 13.1 14 12V3C14 1.9 13.1 1 12 1Z" stroke="currentColor" stroke-width="2"/>
                    <path d="M19 10V12C19 15.866 15.866 19 12 19C8.13401 19 5 15.866 5 12V10" stroke="currentColor" stroke-width="2"/>
                    <path d="M12 19V23M8 23H16" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                </svg>
                <span class="saved-voice-name">${voice.id}</span>
                <span class="gender-badge" title="Gender: ${genderLabel}">${genderLabel}</span>
                ${hasPersonality ? '<span class="personality-badge" title="Has personality">✨</span>' : ''}
            </div>
            ${personalityPreview ? `<div class="saved-voice-personality-preview">${escapeHtml(personalityPreview)}</div>` : ''}
            <div class="saved-voice-actions">
                <button class="edit-voice-btn" onclick="editVoicePersonalityInline('${voice.id}')" title="Edit personality">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" stroke="currentColor" stroke-width="2"/>
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" stroke="currentColor" stroke-width="2"/>
                    </svg>
                </button>
                <button class="delete-voice-btn" onclick="deleteSavedVoice('${voice.id}')" title="Delete voice">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                        <path d="M3 6H5H21" stroke="currentColor" stroke-width="2"/>
                        <path d="M19 6V20C19 21 18 22 17 22H7C6 22 5 21 5 20V6" stroke="currentColor" stroke-width="2"/>
                        <path d="M8 6V4C8 3 9 2 10 2H14C15 2 16 3 16 4V6" stroke="currentColor" stroke-width="2"/>
                    </svg>
                </button>
            </div>
        </div>
    `}).join('');
}

// Escape HTML for safe display
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Edit voice personality inline
function editVoicePersonalityInline(voiceId) {
    const profiles = typeof getVoiceProfiles === 'function' ? getVoiceProfiles() : {};
    const profile = profiles[voiceId] || {};
    
    // Find the voice item
    const savedVoicesListEl = document.getElementById('savedVoicesList');
    if (!savedVoicesListEl) return;
    
    const voiceItem = savedVoicesListEl.querySelector(`[data-voice-id="${voiceId}"]`);
    if (!voiceItem) return;

    // Read the current gender from the badge
    const currentGender = voiceItem.querySelector('.gender-badge')?.textContent?.trim() || 'neutral';
    
    // Replace with edit form
    voiceItem.classList.add('editing');
    voiceItem.innerHTML = `
        <div class="voice-personality-edit-form">
            <div class="edit-form-header">
                <span class="edit-form-title">${voiceId}</span>
            </div>
            <div class="form-group">
                <label>Character Name (optional)</label>
                <input type="text" class="personality-name-input" value="${escapeHtml(profile.name || voiceId)}" placeholder="e.g., Sofia">
            </div>
            <div class="form-group">
                <label>Gender</label>
                <select class="personality-gender-input model-select">
                    <option value="neutral"${currentGender === 'neutral' ? ' selected' : ''}>Neutral</option>
                    <option value="male"${currentGender === 'male' ? ' selected' : ''}>Male</option>
                    <option value="female"${currentGender === 'female' ? ' selected' : ''}>Female</option>
                </select>
            </div>
            <div class="form-group">
                <label>Personality & Background</label>
                <textarea class="personality-text-input" rows="3" placeholder="Describe the character's personality, background, mannerisms...">${escapeHtml(profile.personality || '')}</textarea>
            </div>
            <div class="form-actions">
                <button class="btn-secondary" onclick="cancelEditVoicePersonality('${voiceId}')">Cancel</button>
                <button class="btn-primary" onclick="saveVoicePersonalityInline('${voiceId}')">Save</button>
            </div>
        </div>
    `;
}

// Cancel editing
function cancelEditVoicePersonality(voiceId) {
    // Reload the voices list
    loadSavedVoices();
}

// Save voice personality
function saveVoicePersonalityInline(voiceId) {
    const savedVoicesListEl = document.getElementById('savedVoicesList');
    if (!savedVoicesListEl) return;
    
    const voiceItem = savedVoicesListEl.querySelector(`[data-voice-id="${voiceId}"]`);
    if (!voiceItem) return;
    
    const nameInput = voiceItem.querySelector('.personality-name-input');
    const personalityInput = voiceItem.querySelector('.personality-text-input');
    const genderInput = voiceItem.querySelector('.personality-gender-input');
    
    const name = nameInput?.value?.trim() || voiceId;
    const personality = personalityInput?.value?.trim() || '';
    const gender = genderInput?.value || 'neutral';
    
    // Save using the features.js function if available
    if (typeof saveVoiceProfile === 'function') {
        saveVoiceProfile(voiceId, {
            name: name,
            personality: personality,
            updatedAt: new Date().toISOString()
        });
    } else {
        // Fallback: save directly to localStorage
        const voiceProfilesKey = 'chatbot-voice-profiles';
        const saved = localStorage.getItem(voiceProfilesKey);
        const profiles = saved ? JSON.parse(saved) : {};
        profiles[voiceId] = {
            name: name,
            personality: personality,
            updatedAt: new Date().toISOString()
        };
        localStorage.setItem(voiceProfilesKey, JSON.stringify(profiles));
    }

    // Update gender on the server via PUT endpoint
    fetch(`/api/voice_clones/${encodeURIComponent(voiceId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ gender: gender })
    }).catch(function(e) {
        console.error('[VOICE CLONE] Failed to update gender:', e);
    });
    
    // Reload the voices list
    loadSavedVoices();
}

// Make functions globally accessible
window.editVoicePersonalityInline = editVoicePersonalityInline;
window.cancelEditVoicePersonality = cancelEditVoicePersonality;
window.saveVoicePersonalityInline = saveVoicePersonalityInline;

// Make deleteSavedVoice globally accessible
window.deleteSavedVoice = deleteSavedVoice;

async function deleteSavedVoice(voiceId) {
    if (!confirm(`Are you sure you want to delete voice "${voiceId}"?`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/voice_clones/${encodeURIComponent(voiceId)}`, {
            method: 'DELETE'
        });
        const data = await response.json();
        
        if (data.success) {
            loadSavedVoices();
            // Refresh the TTS speakers dropdown
            if (typeof loadTTSSpeakers === 'function') {
                loadTTSSpeakers();
            }
        } else {
            alert('Error deleting voice: ' + (data.error || 'Unknown error'));
        }
    } catch (e) {
        alert('Error deleting voice: ' + e.message);
    }
}

// Make loadSavedVoices globally accessible for other modules
window.loadSavedVoices = loadSavedVoices;

// ============================================================
// AUDIOBOOK
// ============================================================

// Support both sidebar button formats (expanded and collapsed)
const audiobookBtn = document.getElementById('audiobookBtn') || 
                      document.getElementById('audiobookBtnOption') ||
                      document.getElementById('audiobookBtnCollapsed');

function setupAudiobook() {
    if (!audiobookBtn) return;
    
    audiobookBtn.addEventListener('click', () => {
        if (typeof openAudiobookModal === 'function') {
            openAudiobookModal();
        }
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupAudiobook);
} else {
    setupAudiobook();
}

// ============================================================
// PODCAST
// ============================================================

// Support both sidebar button formats (expanded and collapsed)
const podcastBtn = document.getElementById('podcastBtn') || 
                    document.getElementById('podcastBtnOption') ||
                    document.getElementById('podcastBtnCollapsed');

function setupPodcast() {
    if (!podcastBtn) return;
    
    podcastBtn.addEventListener('click', () => {
        if (typeof openPodcastModal === 'function') {
            openPodcastModal();
        }
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupPodcast);
} else {
    setupPodcast();
}

// ============================================================
// VOICE STUDIO
// ============================================================

const voiceStudioBtns = [
    document.getElementById('voiceStudioBtn'),
    document.getElementById('voiceStudioBtnOption'),
    document.getElementById('voiceStudioBtnCollapsed')
].filter(btn => btn !== null);

function setupVoiceStudio() {
    if (voiceStudioBtns.length === 0) return;

    voiceStudioBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            if (typeof openVoiceStudioModal === 'function') {
                openVoiceStudioModal();
            }
        });
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupVoiceStudio);
} else {
    setupVoiceStudio();
}
