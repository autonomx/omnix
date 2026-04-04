/**
 * Omnix RPG Mode — Production-Grade
 *
 * Implements a mode toggle (Chat / RPG) and the full RPG storytelling UI:
 *   - NarrativeFeed   – scrollable story log with fade-in animation
 *   - ChoicePanel     – action buttons rendered from API choices[]
 *   - NPCPanel        – per-NPC cards with 4-tier relationship bar + structured actions
 *   - DiceRollOverlay – queued, animated roll results (slot-machine style)
 *   - MinimapPanel    – coordinate-aware zone grid with faction colour overlays
 *   - MemoryPanel     – collapsible player memory + world events log
 *
 * Production upgrades:
 *   - State versioning via updateState() reducer (prevents race conditions)
 *   - Dice roll queue (no stacking/overlap on rapid rolls)
 *   - Structured NPC action payloads (JSON, not plain strings)
 *   - Coordinate-based minimap with faction colour overlays
 *   - Frontend state persistence (localStorage snapshot → no blank flash on reload)
 *   - Animated dice rolls (slot-machine number cycling)
 *   - Memory panel showing recent player memory + world events
 *
 * API contract (existing backend):
 *   POST /api/rpg/games              → { session_id, opening, world, player }
 *   POST /api/rpg/games/:id/turn     → { narration, choices?, dice_roll?,
 *                                        events?, fail_state?,
 *                                        npcs?, rolls?, map?,
 *                                        memory?, world_events? }
 *
 * The module does NOT touch any chat logic; it only intercepts the shared
 * send-button / textarea when RPG mode is active.
 */

(function () {
    'use strict';

    // ─── Constants ─────────────────────────────────────────────────────────────

    const STORAGE_KEY       = 'omnix_rpg_session_id';
    const STATE_STORAGE_KEY = 'omnix_rpg_state';
    const DICE_HIDE_DELAY   = 4000;  // ms per roll display
    const DICE_ANIM_FRAMES  = 12;    // number of random-number frames before final
    const DICE_ANIM_INTERVAL = 50;   // ms between animation frames
    // Defer init slightly past chat.js (which defers 500 ms) so that the chat
    // module's event listeners are already attached before we add ours in
    // capture phase.  650 ms > 500 ms + parse time.
    const INIT_DELAY_MS = 650;

    // Faction → colour map for minimap territory overlay
    const FACTION_COLORS = {
        guards: '#3b82f6',
        rebels: '#ef4444',
        merchants: '#f59e0b',
        thieves: '#8b5cf6',
        neutral: '#6b7280',
    };

    // Gender detection heuristics (mirrors audiobook backend)
    const FEMALE_NAMES = new Set([
        'sofia','emma','olivia','ava','mia','charlotte','amelia','luna','harper','aria',
        'ella','elizabeth','camila','gianna','abigail','emily','ella','scarlett','victoria',
        'madison','luna','grace','chloe','penelope','layla','riley','zoey','nora','lily',
        'eleanor','hannah','lillian','addison','aubrey','ellie','stella','natalie','zoe',
        'leah','hazel','violet','aurora','savannah','audrey','brooklyn','bella','claire',
        'skylar','lucy','paisley','everly','anna','alice','freya','lyra','eve','diana',
    ]);
    const MALE_NAMES = new Set([
        'morgan','james','john','robert','michael','david','william','richard','joseph',
        'thomas','charles','christopher','daniel','matthew','anthony','mark','donald',
        'steven','paul','andrew','kenneth','joshua','george','kevin','brian','edward',
        'ronald','timothy','jason','jeffrey','ryan','jacob','gary','nicholas','eric',
        'jonathan','stephen','larry','justin','scott','brandon','benjamin','samuel',
        'frank','gregory','raymond','patrick','alexander','jack','dennis','jerry',
        'liam','noah','ethan','mason','oliver','elijah','aiden','lucas','logan','owen',
        'caleb','henry','wyatt','sebastian','finn','eli','arthur','leo','theo','max',
    ]);

    // ─── State (versioned) ─────────────────────────────────────────────────────

    let stateVersion = 0;

    let rpgState = {
        _v: 0,
        sessionId: null,
        messages: [],      // { type: 'narration'|'event'|'system'|'player', content }
        choices: [],
        npcs: [],
        rolls: [],
        map: null,
        memory: [],        // recent player memory strings
        worldEvents: [],   // recent world event strings
        player: null,      // latest player state from API
        isLoading: false,
        voice_assignments: {}, // speaker -> voice_id
    };

    // TTS settings
    let ttsEnabled = false;
    let narratorVoice = null;    // null = server default
    let availableVoices = [];    // populated on first use
    let currentAudioCtx = null;
    let currentAudioSource = null;

    /** Atomic state updater — increments version, merges patch. */
    function updateState(patch) {
        stateVersion++;
        rpgState = Object.assign({}, rpgState, patch, { _v: stateVersion });
    }

    // ─── Dice Queue ────────────────────────────────────────────────────────────

    const diceQueue = [];
    let isShowingDice = false;

    function enqueueDice(rolls) {
        if (!rolls || !rolls.length) return;
        diceQueue.push.apply(diceQueue, rolls);
        processDiceQueue();
    }

    function processDiceQueue() {
        if (isShowingDice || !diceQueue.length) return;
        isShowingDice = true;
        const roll = diceQueue.shift();
        renderSingleDice(roll);
        setTimeout(function () {
            hideDiceOverlay();
            isShowingDice = false;
            processDiceQueue();
        }, DICE_HIDE_DELAY);
    }

    function hideDiceOverlay() {
        var overlay = el('rpgDiceOverlay');
        if (overlay) overlay.style.display = 'none';
    }

    // ─── DOM helpers ───────────────────────────────────────────────────────────

    function el(id) { return document.getElementById(id); }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    // ─── TTS / Voice ───────────────────────────────────────────────────────────

    /** Detect a character's probable gender from their name. */
    function detectGender(name) {
        if (!name) return 'neutral';
        var lower = name.toLowerCase().trim();
        if (['ms.', 'mrs.', 'she', 'her', 'woman', 'queen', 'princess', 'lady', 'witch'].some(function (w) { return lower.indexOf(w) !== -1; })) return 'female';
        if (['mr.', 'he', 'him', 'man', 'king', 'prince', 'lord', 'wizard', 'knight'].some(function (w) { return lower.indexOf(w) !== -1; })) return 'male';
        var firstName = lower.split(/\s+/)[0].replace(/[^a-z]/g, '');
        if (FEMALE_NAMES.has(firstName)) return 'female';
        if (MALE_NAMES.has(firstName)) return 'male';
        return 'neutral';
    }

    /** Fetch available TTS voices once and cache them. */
    async function fetchVoices() {
        if (availableVoices.length > 0) return availableVoices;
        try {
            var res = await fetch('/api/tts/speakers');
            if (!res.ok) throw new Error('Failed to fetch voices');
            var data = await res.json();
            availableVoices = Array.isArray(data.speakers) ? data.speakers : [];
            // Fallback if empty
            if (availableVoices.length === 0) {
                availableVoices = [
                    {"id": "Maya", "name": "Maya"},
                    {"id": "en", "name": "English Male"},
                    {"id": "en-US", "name": "English Female"},
                    {"id": "es", "name": "Spanish"},
                    {"id": "fr", "name": "French"},
                    {"id": "de", "name": "German"},
                    {"id": "it", "name": "Italian"},
                    {"id": "pt", "name": "Portuguese"},
                    {"id": "ja", "name": "Japanese"},
                    {"id": "ko", "name": "Korean"},
                    {"id": "zh", "name": "Chinese"}
                ];
            }
            populateVoiceSelect();
            return availableVoices;
        } catch (e) {
            // Fallback voices
            availableVoices = [
                {"id": "Maya", "name": "Maya"},
                {"id": "en", "name": "English"},
                {"id": "es", "name": "Spanish"}
            ];
            populateVoiceSelect();
            return availableVoices;
        }
    }

    /** Fill the voice selector dropdown with available speakers. */
    function populateVoiceSelect() {
        var sel = el('rpgVoiceSelect');
        if (!sel || !availableVoices.length) return;
        // Keep the current value if possible
        var current = sel.value;
        sel.innerHTML = '<option value="">Default</option>';
        availableVoices.forEach(function (v) {
            var opt = document.createElement('option');
            opt.value = v.id || v;
            opt.textContent = v.name || v;
            sel.appendChild(opt);
        });
        if (current) sel.value = current;
    }

    /** Play base64-encoded WAV/audio bytes via Web Audio API. */
    function playBase64Audio(b64, sampleRate) {
        try {
            var binary = atob(b64);
            var bytes = Uint8Array.from(binary, function (c) { return c.charCodeAt(0); });

            // Stop any currently playing audio
            if (currentAudioSource) {
                try { currentAudioSource.stop(); } catch (_) {}
                currentAudioSource = null;
            }

            if (!currentAudioCtx || currentAudioCtx.state === 'closed') {
                currentAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
            }

            currentAudioCtx.decodeAudioData(bytes.buffer, function (buf) {
                var src = currentAudioCtx.createBufferSource();
                src.buffer = buf;
                src.connect(currentAudioCtx.destination);
                src.start(0);
                currentAudioSource = src;
            });
        } catch (e) {
            console.warn('[RPG TTS] Audio playback error:', e);
        }
    }

    /**
     * Send text to the TTS endpoint and play the result.
     * speaker – TTS voice name (null = server default / current setting).
     */
    async function speakText(text, speaker) {
        if (!ttsEnabled || !text) return;
        var voiceName = speaker || narratorVoice || undefined;
        try {
            var res = await fetch('/api/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text, speaker: voiceName }),
            });
            if (!res.ok) return;
            var data = await res.json();
            if (data.audio) playBase64Audio(data.audio, data.sample_rate || 24000);
        } catch (e) {
            console.warn('[RPG TTS] Request failed:', e);
        }
    }

    /**
     * Speak the narration text.  Strips markdown/speaker-label prefixes for a
     * cleaner listening experience and resolves NPC voices by gender.
     */
    async function speakNarration(narration) {
        if (!ttsEnabled || !narration) return;

        // Ensure voices are loaded
        await fetchVoices();

        // Find default voices
        var defaultMale = 'en';
        var defaultFemale = 'Maya';
        availableVoices.forEach(function(v) {
            var name = (v.name || v).toLowerCase();
            if (name.includes('male') || name.includes('man') || name.includes('boy')) defaultMale = v.id || v;
            if (name.includes('female') || name.includes('woman') || name.includes('girl')) defaultFemale = v.id || v;
        });

        // Build per-speaker voice map from current NPC list (gender-based)
        var npcVoiceMap = {};
        if (rpgState.npcs && rpgState.npcs.length) {
            rpgState.npcs.forEach(function (npc) {
                if (!npc.name) return;
                var gender = (npc.gender) ? npc.gender.toLowerCase() : detectGender(npc.name + ' ' + (npc.role || ''));
                npcVoiceMap[npc.name.toLowerCase()] = gender;
            });
        }

        // Split narration into segments by speaker label ("Name: text")
        var segments = [];
        var lines = narration.split('\n');
        lines.forEach(function (line) {
            var m = line.match(/^([A-Z][^:]{0,30}):\s*(.+)/);
            if (m) {
                segments.push({ speaker: m[1].trim(), text: m[2].trim() });
            } else if (line.trim()) {
                // Plain narration line — append to last narrator segment or create new one
                if (segments.length && segments[segments.length - 1].speaker === 'Narrator') {
                    segments[segments.length - 1].text += ' ' + line.trim();
                } else {
                    segments.push({ speaker: 'Narrator', text: line.trim() });
                }
            }
        });

        // Play each segment with appropriate voice
        for (var seg of segments) {
            var speaker = seg.speaker;
            var text = seg.text;
            var voice = rpgState.voice_assignments[speaker];
            if (!voice) {
                if (speaker === 'Narrator') {
                    voice = narratorVoice;
                } else {
                    var gender = npcVoiceMap[speaker.toLowerCase()] || detectGender(speaker);
                    voice = gender === 'male' ? defaultMale : defaultFemale;
                }
            }
            await speakText(text, voice);
        }
    }

    // ─── Loading state ─────────────────────────────────────────────────────────

    var loadingInterval = null;
    var ADVENTURE_SETUP_KEY = 'omnix_rpg_adventure_setup';
    var adventureSetup = (function() {
        try {
            var stored = localStorage.getItem(ADVENTURE_SETUP_KEY);
            if (stored) return JSON.parse(stored);
        } catch (e) { /* ignore parse errors */ }
        return { custom_lore: '', custom_rules: '', custom_story: '', world_prompt: '', character_class: '' };
    })();

    /** Always read fresh values from the DOM (if open) or fall back to the
     *  persisted adventureSetup object.  Prevents stale-object bugs. */
    function getAdventureSetupFromUI() {
        return {
            custom_lore: (el('setupCustomLore') ? el('setupCustomLore').value : adventureSetup.custom_lore) || '',
            custom_rules: (el('setupCustomRules') ? el('setupCustomRules').value : adventureSetup.custom_rules) || '',
            custom_story: (el('setupCustomStory') ? el('setupCustomStory').value : adventureSetup.custom_story) || '',
            world_prompt: (el('setupWorldPrompt') ? el('setupWorldPrompt').value : adventureSetup.world_prompt) || '',
            character_class: (el('setupCharacterClass') ? el('setupCharacterClass').value : adventureSetup.character_class) || ''
        };
    }

    function setLoading(loading) {
        updateState({ isLoading: loading });
        if (window._currentMode !== 'rpg') return;
        var sendBtn = el('sendBtn');
        var messageInput = el('messageInput');
        var overlay = el('rpgLoadingOverlay');
        if (!sendBtn || !messageInput) return;
        sendBtn.disabled = loading || !messageInput.value.trim();
        messageInput.disabled = loading;
        if (overlay) {
            if (loading) {
                overlay.style.display = 'flex';
                startLoadingProgress();
            } else {
                overlay.style.display = 'none';
                stopLoadingProgress();
            }
        }
    }

    var generationProgress = { current: 0, total: 6, stage: "Initializing" };

    function updateProgress(stage, step) {
        generationProgress.current = step;
        generationProgress.stage = stage;
        var percent = (step / generationProgress.total) * 100;
        var bar = el('rpgLoadingBar');
        var textEl = el('rpgLoadingText');
        if (bar) bar.style.width = percent + '%';
        if (textEl) textEl.textContent = stage + ' (' + Math.floor(percent) + '%)';
    }

    function startLoadingProgress() {
        if (loadingInterval) clearInterval(loadingInterval);
        generationProgress.current = 0;
        var phases = [
            "Building world",
            "Generating environment",
            "Creating factions",
            "Spawning NPCs",
            "Creating story",
            "Finalizing"
        ];
        var bar = el('rpgLoadingBar');
        if (bar) bar.style.width = '0%';
        updateProgress(phases[0], 0);
        var phaseIndex = 0;
        loadingInterval = setInterval(function() {
            if (phaseIndex < phases.length - 1) {
                phaseIndex++;
                updateProgress(phases[phaseIndex], phaseIndex + 1);
            }
        }, 2000);
    }

    function stopLoadingProgress() {
        if (loadingInterval) {
            clearInterval(loadingInterval);
            loadingInterval = null;
        }
        updateProgress("Adventure ready!", generationProgress.total);
        setTimeout(function() {
            var overlay = el('rpgLoadingOverlay');
            if (overlay) overlay.style.display = 'none';
        }, 500);
    }

    // ─── Voice assignments ────────────────────────────────────────────────────

    function showVoicePanel() {
        closeAllPanels();
        var panel = el('rpgVoicePanel');
        if (!panel) {
            panel = document.createElement('div');
            panel.id = 'rpgVoicePanel';
            panel.className = 'modal';
            panel.innerHTML = '<div class="modal-content" id="rpgVoiceContent"></div>';
            document.body.appendChild(panel);
            panel.addEventListener('click', function(e) {
                if (e.target === panel) panel.classList.remove('active');
            });
        }
        var content = el('rpgVoiceContent');
        content.innerHTML = '<div class="modal-header"><h3>Voice Assignments</h3><button class="modal-close" onclick="document.getElementById(\'rpgVoicePanel\').classList.remove(\'active\');">&times;</button></div><div class="modal-body" id="rpgVoiceBody"></div>';
        var body = el('rpgVoiceBody');
        body.innerHTML = '';
        var speakers = new Set(['Narrator']);
        rpgState.npcs.forEach(function(npc) { if (npc.name) speakers.add(npc.name); });
        speakers.forEach(function(speaker) {
            var div = document.createElement('div');
            div.className = 'voice-assignment';
            var label = document.createElement('label');
            label.textContent = speaker + ': ';
            var sel = document.createElement('select');
            sel.className = 'rpg-voice-select';
            sel.innerHTML = '<option value="">Default</option>';
            availableVoices.forEach(function(v) {
                var opt = document.createElement('option');
                opt.value = v.id || v;
                opt.textContent = v.name || v;
                sel.appendChild(opt);
            });
            sel.value = rpgState.voice_assignments[speaker] || '';
            sel.addEventListener('change', function() {
                rpgState.voice_assignments[speaker] = sel.value || undefined;
                saveVoiceAssignments();
            });
            label.appendChild(sel);
            div.appendChild(label);
            body.appendChild(div);
        });
        panel.classList.add('active');
    }

    async function saveVoiceAssignments() {
        if (!rpgState.sessionId) return;
        try {
            await fetch('/api/rpg/games/' + encodeURIComponent(rpgState.sessionId) + '/voice-assignments', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(rpgState.voice_assignments),
            });
        } catch (e) {}
    }

    // ─── Panel management ─────────────────────────────────────────────────────

    function closeAllPanels() {
        var panels = ['rpgSettingsPanel', 'rpgVoicePanel'];
        panels.forEach(function(id) {
            var p = el(id);
            if (p) p.classList.remove('active');
        });
    }

    // ─── Settings panel ───────────────────────────────────────────────────────

    function showSettingsPanel() {
        closeAllPanels();
        var panel = el('rpgSettingsPanel');
        if (!panel) {
            panel = document.createElement('div');
            panel.id = 'rpgSettingsPanel';
            panel.className = 'modal'; // Use app's modal style
            panel.innerHTML = '<div class="modal-content" id="rpgSettingsContent"></div>';
            document.body.appendChild(panel);
            // Close on backdrop click
            panel.addEventListener('click', function(e) {
                if (e.target === panel) panel.classList.remove('active');
            });
        }
        var content = el('rpgSettingsContent');
        content.innerHTML = '<div class="modal-header"><h3>RPG Settings</h3><button class="modal-close" onclick="document.getElementById(\'rpgSettingsPanel\').classList.remove(\'active\');">&times;</button></div><div class="modal-body" id="rpgSettingsBody"></div>';
        var body = el('rpgSettingsBody');
        body.innerHTML = '';

        // New Game
        var newBtn = document.createElement('button');
        newBtn.className = 'btn btn-primary';
        newBtn.textContent = 'Start New Game';
        newBtn.addEventListener('click', function() {
            resetSession();
            panel.classList.remove('active');
        });
        body.appendChild(newBtn);

        // Load Game
        var loadSection = document.createElement('div');
        loadSection.innerHTML = '<h4>Load Game</h4>';
        var loadContainer = document.createElement('div');
        loadContainer.style.maxHeight = '200px';
        loadContainer.style.overflowY = 'auto';
        fetch('/api/rpg/games').then(r => r.json()).then(data => {
            if (data.games && data.games.length) {
                data.games.forEach(game => {
                    if (!game.id) return; // Skip invalid games
                    var item = document.createElement('div');
                    item.className = 'game-item';
                    item.innerHTML = '<span>' + (game.title || 'Untitled') + ' (' + (game.updated_at || 'Unknown') + ')</span>';
                    var loadBtn = document.createElement('button');
                    loadBtn.className = 'btn btn-secondary';
                    loadBtn.textContent = 'Load';
                    loadBtn.addEventListener('click', function() {
                        loadGame(game.id);
                        panel.classList.remove('active');
                    });
                    var deleteBtn = document.createElement('button');
                    deleteBtn.className = 'btn btn-danger';
                    deleteBtn.textContent = 'Delete';
                    deleteBtn.addEventListener('click', function() {
                        if (confirm('Delete this game?')) {
                            deleteGame(game.id);
                        }
                    });
                    item.appendChild(loadBtn);
                    item.appendChild(deleteBtn);
                    loadContainer.appendChild(item);
                });
            } else {
                loadContainer.innerHTML = '<p>No saved games</p>';
            }
        }).catch(() => {
            loadContainer.innerHTML = '<p>Failed to load games</p>';
        });
        loadSection.appendChild(loadContainer);
        body.appendChild(loadSection);

        // Export and Title
        if (rpgState.sessionId) {
            var manageSection = document.createElement('div');
            manageSection.innerHTML = '<h4>Current Game</h4>';
            var exportBtn = document.createElement('button');
            exportBtn.className = 'btn btn-secondary';
            exportBtn.textContent = 'Export Game';
            exportBtn.addEventListener('click', function() {
                apiGetGame(rpgState.sessionId).then(game => {
                    var blob = new Blob([JSON.stringify(game, null, 2)], {type: 'application/json'});
                    var url = URL.createObjectURL(blob);
                    var a = document.createElement('a');
                    a.href = url;
                    a.download = 'rpg_game_' + rpgState.sessionId + '.json';
                    a.click();
                    URL.revokeObjectURL(url);
                });
            });
            manageSection.appendChild(exportBtn);

            // Game Title
            var titleDiv = document.createElement('div');
            titleDiv.style.marginTop = '10px';
            var input = document.createElement('input');
            input.type = 'text';
            input.placeholder = 'Enter game title';
            input.style.width = '100%';
            input.style.marginBottom = '5px';
            apiGetGame(rpgState.sessionId).then(game => {
                input.value = game.title || '';
            }).catch(() => {});
            var saveTitleBtn = document.createElement('button');
            saveTitleBtn.className = 'btn btn-primary';
            saveTitleBtn.textContent = 'Save Title';
            saveTitleBtn.addEventListener('click', async function() {
                try {
                    await fetch('/api/rpg/games/' + encodeURIComponent(rpgState.sessionId), {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ title: input.value }),
                    });
                    alert('Title saved');
                } catch (e) {
                    alert('Failed to save title');
                }
            });
            titleDiv.appendChild(input);
            titleDiv.appendChild(saveTitleBtn);
            manageSection.appendChild(titleDiv);
            body.appendChild(manageSection);
        }

        panel.classList.add('active');
    }

    async function loadGame(gameId) {
        if (!gameId) return;
        setLoading(true);
        updateState({ sessionId: gameId });
        localStorage.setItem(STORAGE_KEY, gameId);
        try {
            var game = await apiGetGame(gameId);
            updateState({
                player: game.player,
                npcs: game.npcs,
                voice_assignments: game.voice_assignments || {},
                messages: [], // Clear messages for fresh start
            });
            // Clear the feed
            var feed = el('rpgNarrativeFeed');
            if (feed) feed.innerHTML = '<div class="rpg-msg rpg-msg--system">Game loaded. Continue your adventure!</div>';
        } catch (e) {
            alert('Failed to load game');
        } finally {
            setLoading(false);
        }
    }

    async function deleteGame(gameId) {
        if (!gameId) return;
        if (gameId === rpgState.sessionId) {
            alert('Cannot delete the currently loaded game');
            return;
        }
        try {
            await fetch('/api/rpg/games/' + encodeURIComponent(gameId), { method: 'DELETE' });
            // Refresh the list
            showSettingsPanel();
        } catch (e) {
            alert('Failed to delete game');
        }
    }

    // ─── Adventure setup (delegates to Adventure Builder v1) ─────────────────

    function showAdventureSetup() {
        if (typeof AdventureBuilder !== 'undefined') {
            AdventureBuilder.open();
        }
    }

    // ─── API ───────────────────────────────────────────────────────────────────

    async function apiCreateGame(payload) {
        var body = payload || {};
        var res = await fetch('/api/rpg/games', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error('Failed to create game (' + res.status + ')');
        return res.json();
    }

    /**
     * Create a game via the SSE streaming endpoint.  Progress events
     * drive the loading bar in real-time.  Falls back to the standard
     * apiCreateGame if the streaming endpoint is unavailable.
     */
    async function apiCreateGameStream(payload) {
        var body = payload || {};
        try {
            var res = await fetch('/api/rpg/games/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!res.ok) throw new Error('Stream endpoint returned ' + res.status);

            var reader = res.body.getReader();
            var decoder = new TextDecoder();
            var result = null;
            var buffer = '';

            while (true) {
                var chunk = await reader.read();
                if (chunk.done) break;
                buffer += decoder.decode(chunk.value, { stream: true });

                var lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (var i = 0; i < lines.length; i++) {
                    var line = lines[i].trim();
                    if (!line.startsWith('data:')) continue;
                    var jsonStr = line.substring(5).trim();
                    if (!jsonStr) continue;
                    try {
                        var data = JSON.parse(jsonStr);
                    } catch (e) { continue; }

                    if (data.error) throw new Error(data.error);

                    if (data.stage && data.progress) {
                        // Stop the fake fallback timer — real events are arriving
                        if (loadingInterval) {
                            clearInterval(loadingInterval);
                            loadingInterval = null;
                        }
                        updateProgress(data.stage, data.progress);
                    }

                    if (data.result) {
                        result = data.result;
                    }
                }
            }

            if (!result) throw new Error('Stream ended without result');
            return result;
        } catch (err) {
            // Fallback to standard endpoint
            return apiCreateGame(body);
        }
    }

    async function apiGetGame(sessionId) {
        var res = await fetch('/api/rpg/games/' + encodeURIComponent(sessionId));
        if (!res.ok) throw new Error('Failed to get game');
        return res.json();
    }

    async function apiSendTurn(sessionId, input) {
        var res = await fetch('/api/rpg/games/' + encodeURIComponent(sessionId) + '/turn', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ input: input }),
        });
        if (!res.ok) throw new Error('Turn request failed (' + res.status + ')');
        return res.json();
    }

    /**
     * Send a turn via the SSE streaming endpoint.
     * Calls onToken(text) for each streamed token, then returns the full data
     * payload from the final "done" event.
     */
    async function apiSendTurnStream(sessionId, input, onToken) {
        var res = await fetch(
            '/api/rpg/games/' + encodeURIComponent(sessionId) + '/turn/stream',
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ input: input }),
            }
        );
        if (!res.ok) throw new Error('Turn request failed (' + res.status + ')');

        var reader = res.body.getReader();
        var decoder = new TextDecoder();
        var buf = '';
        var finalData = null;

        while (true) {
            var readResult = await reader.read();
            if (readResult.done) break;
            buf += decoder.decode(readResult.value, { stream: true });

            // Parse complete SSE messages (delimited by \n\n)
            var parts = buf.split('\n\n');
            buf = parts.pop(); // keep trailing incomplete chunk

            for (var i = 0; i < parts.length; i++) {
                var part = parts[i];
                if (part.startsWith('data: ')) {
                    try {
                        var evt = JSON.parse(part.slice(6));
                        if (evt.type === 'token' && onToken) {
                            onToken(evt.text);
                        } else if (evt.type === 'done') {
                            finalData = evt;
                        } else if (evt.type === 'error') {
                            throw new Error(evt.error || 'Stream error');
                        }
                    } catch (parseErr) {
                        // ignore malformed SSE line
                    }
                }
            }
        }

        return finalData;
    }

    // ─── Response transform ────────────────────────────────────────────────────

    function transformResponse(data) {
        var messages = [];

        if (data.narration) {
            messages.push({ type: 'narration', content: data.narration });
        }

        if (Array.isArray(data.events)) {
            data.events.forEach(function (ev) {
                var text = ev.description || ev.type || JSON.stringify(ev);
                messages.push({ type: 'event', content: text });
            });
        }

        if (data.fail_state) {
            var text = data.fail_state.description || data.fail_state.type || 'Something went wrong\u2026';
            messages.push({ type: 'system', content: '\u26A0\uFE0F ' + text });
        }

        // Normalise dice rolls: API may return dice_roll (single obj) or rolls (array)
        var rolls = Array.isArray(data.rolls)
            ? data.rolls
            : (data.dice_roll ? [data.dice_roll] : []);

        return {
            messages:    messages,
            choices:     data.choices      || [],
            npcs:        data.npcs         || [],
            rolls:       rolls,
            map:         data.map          || null,
            memory:      data.memory       || [],
            worldEvents: data.world_events || [],
            player:      data.player       || null,
        };
    }

    // ─── Input handler ─────────────────────────────────────────────────────────

    async function handleRPGInput(input) {
        if (!input || rpgState.isLoading) return;

        appendMessage({ type: 'player', content: input });
        setLoading(true);

        // Create a streaming narration element that fills as tokens arrive
        var streamingDiv = null;
        var streamingText = '';

        function onToken(text) {
            var feed = el('rpgNarrativeFeed');
            if (!feed) return;
            var welcome = el('rpgWelcome');
            if (welcome) welcome.style.display = 'none';
            if (!streamingDiv) {
                streamingDiv = document.createElement('div');
                streamingDiv.className = 'rpg-msg rpg-msg--narration rpg-msg--streaming';
                feed.appendChild(streamingDiv);
            }
            streamingText += text;
            streamingDiv.textContent = streamingText;
            feed.scrollTop = feed.scrollHeight;
        }

        /**
         * Send a turn via streaming, falling back to the regular endpoint if
         * the stream returns no data (e.g. on older servers without the endpoint).
         */
        async function doSendTurn(sid) {
            var d = await apiSendTurnStream(sid, input, onToken);
            if (!d) d = await apiSendTurn(sid, input);
            return d;
        }

        try {
            var data;

            if (!rpgState.sessionId) {
                // First input – create game (retry once on failure)
                var retried = false;
                while (true) {
                    try {
                        setLoading(true);
                        var game = await apiCreateGameStream(getAdventureSetupFromUI());
                        setLoading(false);
                        updateState({ sessionId: game.session_id });
                        localStorage.setItem(STORAGE_KEY, rpgState.sessionId);

                        // Show world opening before the player's first turn
                        if (game.opening) {
                            applyUpdate(transformResponse({ narration: game.opening }));
                            speakNarration(game.opening);
                        }

                        data = await doSendTurn(rpgState.sessionId);
                        break;
                    } catch (err) {
                        setLoading(false);
                        if (!retried) {
                            retried = true;
                            updateState({ sessionId: null });
                            localStorage.removeItem(STORAGE_KEY);
                            continue;
                        }
                        throw err;
                    }
                }
            } else {
                // Subsequent turns – retry with a fresh session if the stored one expired
                try {
                    data = await doSendTurn(rpgState.sessionId);
                } catch (err) {
                    updateState({ sessionId: null });
                    localStorage.removeItem(STORAGE_KEY);

                    var game2 = await apiCreateGameStream(getAdventureSetupFromUI());
                    updateState({ sessionId: game2.session_id });
                    localStorage.setItem(STORAGE_KEY, game2.session_id);

                    if (game2.opening) {
                        applyUpdate(transformResponse({ narration: game2.opening }));
                        speakNarration(game2.opening);
                    }

                    data = await doSendTurn(rpgState.sessionId);
                }
            }

            // Remove the streaming placeholder — applyUpdate will add the final
            // narration with markdown rendering
            if (streamingDiv) {
                streamingDiv.remove();
                streamingDiv = null;
                streamingText = '';
            }

            var update = transformResponse(data);
            applyUpdate(update);
            if (update.player) {
                updateState({ player: update.player });
                renderPlayerPanel(update.player);
            }
            // Speak narration after response is complete
            if (data && data.narration) speakNarration(data.narration);
        } catch (err) {
            if (streamingDiv) { streamingDiv.remove(); streamingDiv = null; }
            appendMessage({ type: 'system', content: '\u274C Error: ' + err.message });
        } finally {
            setLoading(false);
            persistSnapshot();
        }
    }

    // ─── Apply update (versioned) ──────────────────────────────────────────────

    function applyUpdate(update) {
        var newMessages = rpgState.messages.concat(update.messages);
        var patch = { messages: newMessages, choices: update.choices };

        // Append new messages to DOM
        update.messages.forEach(function (msg) { appendMessage(msg); });

        if (update.npcs && update.npcs.length) {
            patch.npcs = update.npcs;
        }
        if (update.map) {
            patch.map = update.map;
        }
        if (update.memory && update.memory.length) {
            patch.memory = rpgState.memory.concat(update.memory);
        }
        if (update.worldEvents && update.worldEvents.length) {
            patch.worldEvents = rpgState.worldEvents.concat(update.worldEvents);
        }

        updateState(patch);
        renderChoices();

        if (update.npcs && update.npcs.length) renderNPCs();
        if (update.map) renderMap();
        if (update.memory && update.memory.length) renderMemory();
        if (update.worldEvents && update.worldEvents.length) renderMemory();

        // Dice rolls go through the queue (animated, no overlap)
        if (update.rolls && update.rolls.length) {
            updateState({ rolls: rpgState.rolls.concat(update.rolls) });
            enqueueDice(update.rolls);
        }
    }

    // ─── Rendering: Narrative Feed ─────────────────────────────────────────────

    function appendMessage(msg) {
        var feed = el('rpgNarrativeFeed');
        if (!feed) return;

        // Hide the empty-state welcome card once there is content
        var welcome = el('rpgWelcome');
        if (welcome) welcome.style.display = 'none';

        var div = document.createElement('div');
        div.className = 'rpg-msg rpg-msg--' + msg.type;

        switch (msg.type) {
            case 'narration':
                // Use marked.js if available for light markdown rendering
                div.innerHTML = (typeof marked !== 'undefined')
                    ? marked.parse(msg.content)
                    : escapeHtml(msg.content).replace(/\n/g, '<br>');
                break;

            case 'player':
                div.innerHTML =
                    '<span class="rpg-msg-player-icon">\u203A</span> <em>' + escapeHtml(msg.content) + '</em>';
                break;

            case 'event':
                div.innerHTML =
                    '<span class="rpg-msg-event-icon">\uD83C\uDFB2</span> ' + escapeHtml(msg.content);
                break;

            case 'system':
            default:
                div.textContent = msg.content;
                break;
        }

        feed.appendChild(div);
        feed.scrollTop = feed.scrollHeight;
    }

    // ─── Rendering: Choice Panel ───────────────────────────────────────────────

    function renderChoices() {
        var panel = el('rpgChoicePanel');
        if (!panel) return;

        panel.innerHTML = '';

        if (!rpgState.choices || !rpgState.choices.length) {
            panel.style.display = 'none';
            return;
        }

        panel.style.display = 'flex';
        rpgState.choices.forEach(function (choice) {
            var btn = document.createElement('button');
            btn.className = 'rpg-choice-btn';
            btn.textContent = choice;
            btn.addEventListener('click', function () {
                if (!rpgState.isLoading) handleRPGInput(choice);
            });
            panel.appendChild(btn);
        });
    }

    // ─── Rendering: NPC Panel (structured actions + 4-tier relationship) ──────

    function getMoodClass(mood) {
        if (!mood) return '';
        var m = mood.toLowerCase();
        if (['friendly', 'happy', 'welcoming', 'grateful'].some(function (w) { return m.indexOf(w) !== -1; })) return 'rpg-npc-mood--friendly';
        if (['hostile', 'angry', 'aggressive', 'furious'].some(function (w) { return m.indexOf(w) !== -1; })) return 'rpg-npc-mood--hostile';
        if (['suspicious', 'wary', 'cautious', 'nervous'].some(function (w) { return m.indexOf(w) !== -1; })) return 'rpg-npc-mood--wary';
        return '';
    }

    /** 4-tier relationship colour: green > 50, blue > 0, orange > -50, red. */
    function getRelColor(rel) {
        if (rel > 50) return '#22c55e';   // green — allied
        if (rel > 0)  return '#3b82f6';   // blue  — friendly
        if (rel > -50) return '#f59e0b';  // orange — wary
        return '#ef4444';                  // red   — hostile
    }

    function renderNPCs() {
        var wrapper = el('rpgNPCPanelWrapper');
        var panel = el('rpgNPCPanel');
        if (!panel || !wrapper) return;

        if (!rpgState.npcs || !rpgState.npcs.length) {
            wrapper.style.display = 'none';
            return;
        }

        wrapper.style.display = 'block';
        panel.innerHTML = '';

        rpgState.npcs.forEach(function (npc) {
            var card = document.createElement('div');
            card.className = 'rpg-npc-card';

            var moodClass = getMoodClass(npc.mood);

            // Relationship bar: API uses -100..100; normalise to 0..100%
            var relPct = (npc.relationship != null)
                ? Math.max(0, Math.min(100, (npc.relationship + 100) / 2))
                : null;
            var relColor = (npc.relationship != null) ? getRelColor(npc.relationship) : '#6b7280';
            var relBar = (relPct != null)
                ? '<div class="rpg-npc-rel-bar"><div class="rpg-npc-rel-fill" style="width:' + relPct + '%;background:' + relColor + '"></div></div>'
                : '';

            // Store npc.id (or name as fallback) for structured command payloads
            var npcId = escapeHtml(npc.id || npc.name || '');
            var npcName = escapeHtml(npc.name || 'Unknown');

            card.innerHTML =
                '<div class="rpg-npc-name">' + npcName + '</div>' +
                '<div class="rpg-npc-mood ' + moodClass + '">' + escapeHtml(npc.mood || '') + '</div>' +
                relBar +
                '<div class="rpg-npc-actions">' +
                    '<button class="rpg-npc-btn" data-npc-id="' + npcId + '" data-npc-name="' + npcName + '" data-action="talk">Talk</button>' +
                    '<button class="rpg-npc-btn rpg-npc-btn--threat" data-npc-id="' + npcId + '" data-npc-name="' + npcName + '" data-action="threaten">Threaten</button>' +
                '</div>';

            // Structured NPC action: send JSON payload so the backend can evolve
            // without fragile string parsing.
            card.querySelectorAll('.rpg-npc-btn').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    if (rpgState.isLoading) return;
                    var payload = JSON.stringify({
                        type: 'npc_action',
                        npc_id: btn.dataset.npcId,
                        action: btn.dataset.action,
                    });
                    handleRPGInput(payload);
                });
            });

            panel.appendChild(card);
        });
    }

    // ─── Rendering: Dice Roll (single, animated) ──────────────────────────────

    function renderSingleDice(roll) {
        var overlay = el('rpgDiceOverlay');
        if (!overlay) return;

        var success = roll.success !== false;
        var total   = roll.total  != null ? roll.total : roll.result;
        var label   = roll.type   || roll.dice || 'd20';
        var modStr  = (roll.modifier != null && roll.modifier !== 0)
            ? ' + ' + roll.modifier
            : '';

        var cls = success ? 'rpg-dice-roll--success' : 'rpg-dice-roll--fail';
        var badgeCls = success ? 'rpg-dice-badge--success' : 'rpg-dice-badge--fail';
        var badge = success ? '\u2713' : '\u2717';

        overlay.innerHTML =
            '<div class="rpg-dice-roll ' + cls + '">' +
                '\uD83C\uDFB2 ' + escapeHtml(label) + ': ' +
                '<span class="rpg-dice-value" id="rpgDiceAnimValue">' + roll.result + '</span>' +
                modStr + ' = <strong>' + total + '</strong>' +
                '<span class="rpg-dice-badge ' + badgeCls + '">' + badge + '</span>' +
            '</div>';

        overlay.style.display = 'flex';

        // Animate: slot-machine style number cycling
        animateDiceValue(el('rpgDiceAnimValue'), roll.result);
    }

    /** Slot-machine style dice animation — cycles random numbers then lands on final. */
    function animateDiceValue(element, finalValue) {
        if (!element) return;
        var i = 0;
        var maxVal = 20; // assume d20 max
        var interval = setInterval(function () {
            element.textContent = Math.floor(Math.random() * maxVal) + 1;
            i++;
            if (i >= DICE_ANIM_FRAMES) {
                clearInterval(interval);
                element.textContent = finalValue;
                element.classList.add('rpg-dice-value--final');
            }
        }, DICE_ANIM_INTERVAL);
    }

    // ─── Rendering: Minimap (coordinate-aware + faction colours) ──────────────

    function renderMap() {
        var panel   = el('rpgMinimapPanel');
        var minimap = el('rpgMinimap');
        if (!panel || !minimap || !rpgState.map) return;

        var map = rpgState.map;
        if (!Array.isArray(map.zones) || !map.zones.length) {
            panel.style.display = 'none';
            return;
        }

        panel.style.display = 'block';

        // Determine if zones have coordinates
        var hasCoords = map.zones.some(function (z) { return z.x != null && z.y != null; });

        if (hasCoords) {
            // Compute grid bounds
            var maxX = 1, maxY = 1;
            map.zones.forEach(function (z) {
                if (z.x != null && z.x > maxX) maxX = z.x;
                if (z.y != null && z.y > maxY) maxY = z.y;
            });
            minimap.style.gridTemplateColumns = 'repeat(' + maxX + ', 1fr)';
            minimap.style.gridTemplateRows = 'repeat(' + maxY + ', 1fr)';
        } else {
            // Fallback: 3-column grid
            minimap.style.gridTemplateColumns = 'repeat(3, 1fr)';
            minimap.style.gridTemplateRows = '';
        }

        // Player position (if provided)
        var playerZone = (map.player && map.player.zone) || map.current_zone;

        minimap.innerHTML = map.zones.map(function (zone) {
            var isActive    = zone.id === playerZone;
            var dangerClass = zone.danger >= 4 ? 'rpg-zone--danger'
                            : zone.danger >= 2 ? 'rpg-zone--caution'
                            : '';
            var ownerTitle  = zone.owner ? ' title="Owner: ' + escapeHtml(zone.owner) + '"' : '';

            // Faction colour overlay
            var bgStyle = '';
            if (zone.owner && FACTION_COLORS[zone.owner]) {
                bgStyle = 'background-color:' + FACTION_COLORS[zone.owner] + ';opacity:0.85;';
            }

            // Coordinate placement
            var posStyle = '';
            if (hasCoords && zone.x != null && zone.y != null) {
                posStyle = 'grid-column:' + zone.x + ';grid-row:' + zone.y + ';';
            }

            // Active zone overrides faction colour
            var activeStyle = isActive
                ? 'background:var(--accent);border-color:var(--accent);color:#fff;'
                : bgStyle;

            return '<div class="rpg-zone ' + (isActive ? 'rpg-zone--active' : '') + ' ' + dangerClass + '"' +
                ownerTitle +
                ' style="' + posStyle + activeStyle + '">' +
                escapeHtml(zone.id || '?') +
            '</div>';
        }).join('');
    }

    // ─── Rendering: Memory Panel ───────────────────────────────────────────────

    function renderMemory() {
        var panelWrapper = el('rpgMemoryPanelWrapper');
        var memList      = el('rpgMemoryList');
        var eventsList   = el('rpgWorldEventsList');
        if (!panelWrapper) return;

        var hasMemory = rpgState.memory && rpgState.memory.length;
        var hasEvents = rpgState.worldEvents && rpgState.worldEvents.length;

        if (!hasMemory && !hasEvents) {
            panelWrapper.style.display = 'none';
            return;
        }

        panelWrapper.style.display = 'block';

        if (memList && hasMemory) {
            // Show last 5 memory entries
            memList.innerHTML = rpgState.memory.slice(-5).map(function (m) {
                return '<li class="rpg-memory-item">' + escapeHtml(m) + '</li>';
            }).join('');
        }

        if (eventsList && hasEvents) {
            // Show last 5 world events
            eventsList.innerHTML = rpgState.worldEvents.slice(-5).map(function (e) {
                return '<li class="rpg-memory-item rpg-memory-item--event">' + escapeHtml(e) + '</li>';
            }).join('');
        }
    }

    // ─── Rendering: Player Stats / Inventory Panel ─────────────────────────────

    function renderPlayerPanel(player) {
        var panel = el('rpgPlayerPanel');
        if (!panel || !player) return;

        var stats = player.stats || {};
        var inventory = Array.isArray(player.inventory) ? player.inventory : [];
        var quests = Array.isArray(player.quests_active) ? player.quests_active : [];
        var factionRep = player.reputation_factions || {};
        var skills = player.skills || {};

        // Level / XP bar
        var levelHtml = '';
        if (player.level !== undefined) {
            var xpPercent = player.xp_to_next > 0 ? Math.floor((player.xp / player.xp_to_next) * 100) : 0;
            levelHtml =
                '<div class="rpg-player-level">' +
                    '<span class="rpg-level-badge">Lv ' + (player.level || 1) + '</span>' +
                    (player.character_class ? '<span class="rpg-class-badge">' + escapeHtml(player.character_class) + '</span>' : '') +
                    '<div class="rpg-xp-bar"><div class="rpg-xp-fill" style="width:' + xpPercent + '%"></div>' +
                    '<span class="rpg-xp-text">XP ' + (player.xp || 0) + '/' + (player.xp_to_next || 100) + '</span></div>' +
                '</div>';
        }

        // HP / Stamina / Mana bars
        var vitalsHtml = '';
        if (player.max_hp !== undefined) {
            var hpPct = player.max_hp > 0 ? Math.floor(((player.hp || 0) / player.max_hp) * 100) : 0;
            var stPct = player.max_stamina > 0 ? Math.floor(((player.stamina || 0) / player.max_stamina) * 100) : 0;
            var mpPct = player.max_mana > 0 ? Math.floor(((player.mana || 0) / player.max_mana) * 100) : 0;
            vitalsHtml =
                '<div class="rpg-player-vitals">' +
                    '<div class="rpg-vital-row">❤️ HP <div class="rpg-vital-bar rpg-vital-hp"><div class="rpg-vital-fill" style="width:' + hpPct + '%"></div></div> ' + (player.hp || 0) + '/' + (player.max_hp || 0) + '</div>' +
                    '<div class="rpg-vital-row">⚡ STA <div class="rpg-vital-bar rpg-vital-sta"><div class="rpg-vital-fill" style="width:' + stPct + '%"></div></div> ' + (player.stamina || 0) + '/' + (player.max_stamina || 0) + '</div>' +
                    '<div class="rpg-vital-row">🔮 MP <div class="rpg-vital-bar rpg-vital-mp"><div class="rpg-vital-fill" style="width:' + mpPct + '%"></div></div> ' + (player.mana || 0) + '/' + (player.max_mana || 0) + '</div>' +
                '</div>';
        }

        // Stats rows
        var statsHtml =
            '<div class="rpg-player-stats">' +
                '<div class="rpg-stat"><span class="rpg-stat-label">⚔️ STR</span><span class="rpg-stat-value">' + (stats.strength || 0) + '</span></div>' +
                '<div class="rpg-stat"><span class="rpg-stat-label">🏹 DEX</span><span class="rpg-stat-value">' + (stats.dexterity || 0) + '</span></div>' +
                '<div class="rpg-stat"><span class="rpg-stat-label">🛡️ CON</span><span class="rpg-stat-value">' + (stats.constitution || 0) + '</span></div>' +
                '<div class="rpg-stat"><span class="rpg-stat-label">🧠 INT</span><span class="rpg-stat-value">' + (stats.intelligence || 0) + '</span></div>' +
                '<div class="rpg-stat"><span class="rpg-stat-label">🔮 WIS</span><span class="rpg-stat-value">' + (stats.wisdom || 0) + '</span></div>' +
                '<div class="rpg-stat"><span class="rpg-stat-label">💬 CHA</span><span class="rpg-stat-value">' + (stats.charisma || 0) + '</span></div>' +
                '<div class="rpg-stat"><span class="rpg-stat-label">💰 Gold</span><span class="rpg-stat-value">' + (stats.wealth || 0) + '</span></div>' +
            '</div>';

        // Skills section
        var skillKeys = Object.keys(skills);
        var skillHtml = '';
        if (skillKeys.length) {
            skillHtml = '<div class="rpg-player-section-title">🎯 Skills</div><div class="rpg-player-skills">' +
                skillKeys.map(function(sk) {
                    var lvl = typeof skills[sk] === 'number' ? skills[sk] : (skills[sk] && skills[sk].level || 0);
                    return '<span class="rpg-skill-badge">' + escapeHtml(sk) + ' <strong>' + lvl + '</strong></span>';
                }).join('') + '</div>';
        }

        // Unspent stat points
        var pointsHtml = '';
        if (player.unspent_points && player.unspent_points > 0) {
            pointsHtml = '<div class="rpg-unspent-points">🌟 Unspent stat points: <strong>' + player.unspent_points + '</strong></div>';
        }

        // Location
        var locHtml = player.location
            ? '<div class="rpg-player-location">📍 ' + escapeHtml(player.location) + '</div>'
            : '';

        // Reputation
        var repHtml = '';
        if (player.reputation_local || player.reputation_global) {
            repHtml = '<div class="rpg-player-rep">Local rep: <strong>' + (player.reputation_local || 0) +
                      '</strong> &nbsp; Global: <strong>' + (player.reputation_global || 0) + '</strong></div>';
        }

        // Faction reputations
        var factionHtml = '';
        var factionKeys = Object.keys(factionRep);
        if (factionKeys.length) {
            factionHtml = '<div class="rpg-player-factions">' +
                factionKeys.map(function (f) {
                    return '<span class="rpg-faction-badge">' + escapeHtml(f) + ': ' + factionRep[f] + '</span>';
                }).join('') + '</div>';
        }

        // Inventory
        var invHtml = '<div class="rpg-player-section-title">🎒 Inventory</div>';
        if (inventory.length) {
            invHtml += '<ul class="rpg-inventory-list">' +
                inventory.map(function (item) {
                    return '<li class="rpg-inventory-item">' + escapeHtml(item) + '</li>';
                }).join('') + '</ul>';
        } else {
            invHtml += '<p class="rpg-empty-note">Empty</p>';
        }

        // Active quests
        var questHtml = '';
        if (quests.length) {
            questHtml = '<div class="rpg-player-section-title">📜 Quests</div>' +
                '<ul class="rpg-inventory-list">' +
                quests.map(function (q) {
                    return '<li class="rpg-inventory-item">' + escapeHtml(q) + '</li>';
                }).join('') + '</ul>';
        }

        panel.innerHTML =
            '<div class="rpg-player-name">' + escapeHtml(player.name || 'Player') + '</div>' +
            levelHtml + vitalsHtml + locHtml + statsHtml + pointsHtml + skillHtml + repHtml + factionHtml + invHtml + questHtml;
    }

    /** Open the player stats/inventory modal overlay. */
    function openPlayerPanel() {
        // Refresh from current state, or fetch fresh from API if no data yet
        var overlay = el('rpgPlayerPanelOverlay');
        if (!overlay) return;
        if (rpgState.player) {
            renderPlayerPanel(rpgState.player);
        } else if (rpgState.sessionId) {
            fetch('/api/rpg/games/' + encodeURIComponent(rpgState.sessionId) + '/player')
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    if (data.player) {
                        updateState({ player: data.player });
                        renderPlayerPanel(data.player);
                    }
                })
                .catch(function () {});
        }
        overlay.style.display = 'flex';
    }

    /** Close the player stats/inventory overlay. */
    function closePlayerPanel() {
        var overlay = el('rpgPlayerPanelOverlay');
        if (overlay) overlay.style.display = 'none';
    }

    // ─── Mode switching ────────────────────────────────────────────────────────

    function switchMode(mode) {
        window._currentMode = mode;

        var chatContainer = el('chatContainer');
        var rpgView       = el('rpgView');
        var chatModeBtn   = el('chatModeBtn');
        var rpgModeBtn    = el('rpgModeBtn');
        var messageInput  = el('messageInput');
        var sendBtn       = el('sendBtn');

        if (mode === 'rpg') {
            if (chatContainer) chatContainer.style.display = 'none';
            if (rpgView)       rpgView.style.display = 'flex';
            if (chatModeBtn)   chatModeBtn.classList.remove('active');
            if (rpgModeBtn)    rpgModeBtn.classList.add('active');
            if (messageInput)  messageInput.placeholder = 'What do you do?';
            if (sendBtn && messageInput) {
                sendBtn.disabled = !messageInput.value.trim() || rpgState.isLoading;
            }

            // Load game state if session exists
            if (rpgState.sessionId) {
                apiGetGame(rpgState.sessionId).then(function(game) {
                    updateState({
                        player: game.player,
                        npcs: game.npcs,
                        voice_assignments: game.voice_assignments || {},
                    });
                }).catch(function() {});
            }

            // Set up toolbar buttons
            var voiceBtn = el('rpgVoiceBtn');
            if (voiceBtn) voiceBtn.addEventListener('click', showVoicePanel);

            var settingsBtn = el('rpgSettingsBtn');
            if (settingsBtn) settingsBtn.addEventListener('click', showSettingsPanel);
        } else {
            if (chatContainer) chatContainer.style.display = '';
            if (rpgView)       rpgView.style.display = 'none';
            if (chatModeBtn)   chatModeBtn.classList.add('active');
            if (rpgModeBtn)    rpgModeBtn.classList.remove('active');
            if (messageInput)  messageInput.placeholder = 'Type your message\u2026';
            if (sendBtn && messageInput) {
                sendBtn.disabled = !messageInput.value.trim();
            }
        }
    }

    // ─── Shared input intercept ────────────────────────────────────────────────
    //
    // We listen in the *capture* phase so our handler fires before the existing
    // chat handlers (which listen in the bubble phase).  When not in RPG mode
    // we bail immediately and let the normal chat flow proceed.

    function setupInputIntercept() {
        var sendBtn      = el('sendBtn');
        var messageInput = el('messageInput');
        if (!sendBtn || !messageInput) return;

        sendBtn.addEventListener('click', function (e) {
            if (window._currentMode !== 'rpg') return;
            e.stopImmediatePropagation();
            var input = messageInput.value.trim();
            if (!input || rpgState.isLoading) return;
            messageInput.value = '';
            messageInput.style.height = 'auto';
            sendBtn.disabled = true;
            handleRPGInput(input);
        }, true /* capture */);

        messageInput.addEventListener('keydown', function (e) {
            if (window._currentMode !== 'rpg') return;
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                e.stopImmediatePropagation();
                var input = messageInput.value.trim();
                if (!input || rpgState.isLoading) return;
                messageInput.value = '';
                messageInput.style.height = 'auto';
                sendBtn.disabled = true;
                handleRPGInput(input);
            }
        }, true /* capture */);

        // Keep send button enabled/disabled in sync while in RPG mode
        messageInput.addEventListener('input', function () {
            if (window._currentMode !== 'rpg') return;
            if (sendBtn) sendBtn.disabled = !messageInput.value.trim() || rpgState.isLoading;
        });
    }

    // ─── Collapsible side-panels ───────────────────────────────────────────────

    function setupCollapsible() {
        document.querySelectorAll('.rpg-panel-collapse').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var target = el(btn.dataset.target);
                if (!target) return;
                var collapsed = target.style.display === 'none';
                target.style.display = collapsed ? '' : 'none';
                btn.textContent = collapsed ? '\u25BC' : '\u25B6';
            });
        });
    }

    // ─── Welcome card helper ───────────────────────────────────────────────────
    //
    // Centralises the welcome-card HTML so that both the initial DOM (index.html)
    // and the resetSession() rebuild produce identical markup, keeping the
    // New Adventure button always present and delegated via the feed's click
    // listener (set up once in init()).

    function buildWelcomeHTML() {
        return '<div class="rpg-welcome" id="rpgWelcome">' +
                    '<div class="rpg-welcome-icon">\u2694\uFE0F</div>' +
                    '<h3>RPG Mode</h3>' +
                    '<p>Type anything to begin your adventure, or set up a custom world\u2026</p>' +
                    '<button class="rpg-new-session-btn" id="rpgNewSessionBtn" title="Start a fresh adventure">New Adventure</button>' +
                    '<button class="rpg-setup-btn" id="rpgSetupBtn" title="Customise your world before starting">⚙️ Adventure Setup</button>' +
                '</div>';
    }

    // ─── Adventure Setup Modal (v1 — delegates to Adventure Builder) ──────────
    //
    // The legacy buildSetupModal / showSetupModal are replaced by the
    // Adventure Builder wizard.  These thin wrappers remain so that any
    // existing callers still work.

    function buildSetupModal() {
        // No-op: the Adventure Builder overlay is created lazily by AdventureBuilder.open()
    }

    function showSetupModal() {
        if (typeof AdventureBuilder !== 'undefined') {
            AdventureBuilder.open();
        }
    }

    function closeSetupModal() {
        if (typeof AdventureBuilder !== 'undefined') {
            AdventureBuilder.close();
        }
    }

    /** Start a new game with custom parameters from the setup modal. */
    async function startGameWithPayload(payload) {
        setLoading(true);
        try {
            var game = await apiCreateGame(payload);
            updateState({ sessionId: game.session_id });
            localStorage.setItem(STORAGE_KEY, rpgState.sessionId);

            if (game.opening && game.opening.trim()) {
                applyUpdate(transformResponse({ narration: game.opening }));
            }
        } catch (err) {
            appendMessage({ type: 'system', content: '\u274C Error: ' + err.message });
        } finally {
            setLoading(false);
            persistSnapshot();
        }
    }

    // ─── Frontend state persistence ────────────────────────────────────────────
    //
    // Saves a lightweight snapshot (messages, map, memory, worldEvents) to
    // localStorage so that a page reload doesn't show a blank RPG view.

    function persistSnapshot() {
        try {
            var snapshot = {
                messages:    rpgState.messages,
                map:         rpgState.map,
                memory:      rpgState.memory,
                worldEvents: rpgState.worldEvents,
                choices:     rpgState.choices,
                npcs:        rpgState.npcs,
                player:      rpgState.player,
            };
            localStorage.setItem(STATE_STORAGE_KEY, JSON.stringify(snapshot));
        } catch (e) {
            // localStorage full or unavailable — silently skip
        }
    }

    function hydrateFromSnapshot() {
        try {
            var raw = localStorage.getItem(STATE_STORAGE_KEY);
            if (!raw) return false;
            var snapshot = JSON.parse(raw);
            if (!snapshot || !Array.isArray(snapshot.messages) || !snapshot.messages.length) return false;

            updateState({
                messages:    snapshot.messages    || [],
                map:         snapshot.map         || null,
                memory:      snapshot.memory      || [],
                worldEvents: snapshot.worldEvents || [],
                choices:     snapshot.choices     || [],
                npcs:        snapshot.npcs        || [],
                player:      snapshot.player      || null,
            });

            // Re-render the feed from the snapshot
            var welcome = el('rpgWelcome');
            if (welcome) welcome.style.display = 'none';

            rpgState.messages.forEach(function (msg) { appendMessage(msg); });
            renderChoices();
            if (rpgState.npcs && rpgState.npcs.length) renderNPCs();
            if (rpgState.map) renderMap();
            if ((rpgState.memory && rpgState.memory.length) ||
                (rpgState.worldEvents && rpgState.worldEvents.length)) {
                renderMemory();
            }
            if (rpgState.player) renderPlayerPanel(rpgState.player);

            return true;
        } catch (e) {
            return false;
        }
    }

    // ─── Reset / new-session ───────────────────────────────────────────────────

    function resetSession() {
        updateState({
            sessionId:   null,
            messages:    [],
            choices:     [],
            npcs:        [],
            rolls:       [],
            map:         null,
            memory:      [],
            worldEvents: [],
            player:      null,
        });
        localStorage.removeItem(STORAGE_KEY);
        localStorage.removeItem(STATE_STORAGE_KEY);

        // Clear dice queue
        diceQueue.length = 0;
        isShowingDice = false;

        var feed = el('rpgNarrativeFeed');
        if (feed) feed.innerHTML = buildWelcomeHTML();
        // Note: the "New Adventure" button click is handled via event delegation
        // on rpgNarrativeFeed (set up in init()), so no extra listener needed here.

        var choicePanel = el('rpgChoicePanel');
        if (choicePanel) { choicePanel.style.display = 'none'; choicePanel.innerHTML = ''; }

        var npcWrapper = el('rpgNPCPanelWrapper');
        if (npcWrapper) npcWrapper.style.display = 'none';

        var diceOverlay = el('rpgDiceOverlay');
        if (diceOverlay) diceOverlay.style.display = 'none';

        var minimapPanel = el('rpgMinimapPanel');
        if (minimapPanel) minimapPanel.style.display = 'none';

        var memoryPanel = el('rpgMemoryPanelWrapper');
        if (memoryPanel) memoryPanel.style.display = 'none';

        var playerPanel = el('rpgPlayerPanel');
        if (playerPanel) playerPanel.innerHTML = '';

        closePlayerPanel();

        // Open the Adventure Builder after reset so the user gets the
        // structured wizard instead of falling through to a raw text input.
        if (typeof AdventureBuilder !== 'undefined') {
            AdventureBuilder.open();
        }
    }

    // ─── Init ──────────────────────────────────────────────────────────────────

    function init() {
        console.log('[RPG] Initializing RPG mode\u2026');

        window._currentMode = 'chat';

        // ── Adventure Builder launch callback ──────────────────────────────
        // When the builder successfully launches an adventure, pipe the
        // result into the RPG feed just like legacy game creation.
        window._onAdventureBuilderLaunch = function (res) {
            updateState({ sessionId: res.session_id });
            localStorage.setItem(STORAGE_KEY, rpgState.sessionId);
            if (res.opening && res.opening.trim()) {
                applyUpdate(transformResponse({ narration: res.opening }));
            }
            if (res.npcs && res.npcs.length) {
                updateState({ npcs: res.npcs });
                renderNPCs();
            }
            if (res.memory && res.memory.length) {
                updateState({ memory: res.memory });
            }
            if (res.worldEvents && res.worldEvents.length) {
                updateState({ worldEvents: res.worldEvents });
            }
            persistSnapshot();
        };

        // Restore persisted session id (will retry fresh session on first failure)
        var storedId = localStorage.getItem(STORAGE_KEY);
        if (storedId) updateState({ sessionId: storedId });

        // Hydrate UI from snapshot (prevents blank flash on reload)
        if (rpgState.sessionId) {
            hydrateFromSnapshot();
        }

        // Mode toggle
        var chatModeBtn = el('chatModeBtn');
        var rpgModeBtn  = el('rpgModeBtn');
        if (chatModeBtn) chatModeBtn.addEventListener('click', function () { switchMode('chat'); });
        if (rpgModeBtn)  rpgModeBtn.addEventListener('click',  function () { switchMode('rpg'); });

        // "New Adventure" and "Adventure Setup" buttons — use event delegation on
        // the feed so the listener survives the innerHTML replacement in resetSession().
        var feed = el('rpgNarrativeFeed');

        // Adventure Setup button
        var rpgSetupBtn = el('rpgSetupBtn');
        if (rpgSetupBtn) rpgSetupBtn.addEventListener('click', showAdventureSetup);
        if (feed) {
            feed.addEventListener('click', function (e) {
                if (e.target && e.target.id === 'rpgNewSessionBtn') resetSession();
                if (e.target && e.target.id === 'rpgSetupBtn') showSetupModal();
            });
        }

        // Stats / inventory panel button
        var statsBtn = el('rpgStatsBtn');
        if (statsBtn) statsBtn.addEventListener('click', openPlayerPanel);

        // Close player panel overlay on backdrop click or close button
        var playerOverlay = el('rpgPlayerPanelOverlay');
        if (playerOverlay) {
            playerOverlay.addEventListener('click', function (e) {
                if (e.target === playerOverlay) closePlayerPanel();
            });
        }
        var playerCloseBtn = el('rpgPlayerPanelClose');
        if (playerCloseBtn) playerCloseBtn.addEventListener('click', closePlayerPanel);

        // TTS toggle
        var ttsToggle = el('rpgTtsToggle');
        if (ttsToggle) {
            ttsEnabled = ttsToggle.checked;
            ttsToggle.addEventListener('change', function () {
                ttsEnabled = ttsToggle.checked;
                if (ttsEnabled) fetchVoices();
            });
        }

        // Voice selector
        var voiceSel = el('rpgVoiceSelect');
        if (voiceSel) {
            voiceSel.addEventListener('change', function () {
                narratorVoice = voiceSel.value || null;
            });
            if (ttsEnabled) fetchVoices();
        }

        // Sidebar shortcuts (expanded + collapsed)
        ['rpgBtnOption', 'rpgBtnCollapsed'].forEach(function (id) {
            var btn = el(id);
            if (btn) btn.addEventListener('click', function () { switchMode('rpg'); });
        });

        setupCollapsible();
        setupInputIntercept();

        console.log('[RPG] RPG mode ready (state v' + stateVersion + ')');
    }

    // Defer until after all other scripts have initialised
    document.addEventListener('DOMContentLoaded', function () { setTimeout(init, INIT_DELAY_MS); });

    // Public API (handy for debugging from the console)
    window.RPGMode = {
        get state() { return rpgState; },
        get version() { return stateVersion; },
        reset:       resetSession,
        switchMode:  switchMode,
        handleInput: handleRPGInput,
    };
}());
