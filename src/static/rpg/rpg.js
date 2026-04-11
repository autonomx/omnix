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
 * API contract (canonical session backend):
 *   POST /api/rpg/adventure/start    → { session_id, opening, world, player }
 *   POST /api/rpg/session/turn       → { narration, choices?, dice_roll?,
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
    const TYPING_IDLE_MS = 1500;
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
        // Living-world ambient state (Phase 8)
        sessionStream: null,
        ambientSeq: 0,
        unreadAmbient: 0,
        isTyping: false,
        heartbeatTimer: null,
        pollTimer: null,
        ambientFeedBuffer: [],
        // Settings and world events (Living World v2)
        settings: {},
        worldEventsView: {
            local_events: [],
            global_events: [],
            director_pressure: [],
            recent_changes: [],
        },
        worldEventsSummary: {},
        worldEventsTab: 'local',
    };

    let typingIdleTimer = null;

    // ─── Console Debug Logger ──────────────────────────────────────────────────

    function rpgDebugEnabled() {
        return !!(rpgState && rpgState.settings && rpgState.settings.console_debug_enabled);
    }

    function rpgDebug(tag, payload) {
        if (!rpgDebugEnabled()) return;
        try {
            console.groupCollapsed('[RPG][' + tag + ']');
            console.log(payload);
            console.groupEnd();
        } catch (e) {
            console.log('[RPG][' + tag + ']', payload);
        }
    }

    function _safeArray(v) {
        return Array.isArray(v) ? v : [];
    }

    function _safeObj(v) {
        return (v && typeof v === 'object' && !Array.isArray(v)) ? v : {};
    }

    function _safeStr(v) {
        return (v == null) ? '' : String(v);
    }

    function _nonEmptySection(lines) {
        return _safeArray(lines).filter(Boolean);
    }

    function _coerceWorldAdvanceRecap(payload) {
        payload = _safeObj(payload);

        var nested =
            _safeObj(payload.world_advance_recap).summary ? _safeObj(payload.world_advance_recap) :
            _safeObj(payload.resume_recap).summary ? _safeObj(payload.resume_recap) :
            _safeObj(payload.recap).summary ? _safeObj(payload.recap) :
            _safeObj(payload.resume_summary).summary ? _safeObj(payload.resume_summary) :
            {};

        if (Object.keys(nested).length) {
            payload = Object.assign({}, payload, nested);
        }

        return {
            summary: _safeStr(payload.summary || payload.message || payload.text),
            additional_moments: payload.additional_moments || payload.advanced_moments || payload.world_advance_count || payload.moments || 0,
            director_activity: _safeArray(payload.director_activity),
            director_notes: _safeArray(payload.director_notes),
            world_events: _safeArray(payload.world_events || payload.recent_world_events),
            incidents: _safeArray(payload.incidents || payload.recent_incidents),
            consequences: _safeArray(payload.consequences || payload.recent_consequences),
            threads: _safeArray(payload.threads || payload.active_threads),
            factions: _safeArray(payload.factions || payload.faction_activity),
            npc_updates: _safeArray(payload.npc_updates || payload.character_updates),
            location_updates: _safeArray(payload.location_updates),
            changes: _safeArray(payload.changes),
        };
    }

    function _takeTextList(items, limit) {
        return _safeArray(items)
            .map(function (item) {
                if (typeof item === 'string') return item.trim();
                item = _safeObj(item);
                return (
                    _safeStr(item.summary).trim() ||
                    _safeStr(item.text).trim() ||
                    _safeStr(item.label).trim() ||
                    _safeStr(item.title).trim() ||
                    _safeStr(item.name).trim() ||
                    _safeStr(item.description).trim()
                );
            })
            .filter(Boolean)
            .slice(0, limit || 5);
    }

    function _renderBulletSection(title, lines) {
        lines = _nonEmptySection(lines);
        if (!lines.length) return '';
        return '**' + title + ':**\n' + lines.map(function (x) {
            return '- ' + x;
        }).join('\n');
    }

    function buildWorldAdvanceRecapMarkdown(payload) {
        payload = _safeObj(payload);
        if (!payload) return '📜 While you were away, the world advanced.';

        var lines = [];
        var summary = _safeStr(payload.summary);
        var moments = Number(payload.additional_moments || 0);

        if (summary) {
            lines.push('📜 ' + summary);
        } else if (moments > 0) {
            lines.push('📜 While you were away, the world advanced through ' + moments + ' additional moments.');
        } else {
            lines.push('📜 While you were away, the world advanced.');
        }

        function pushSection(title, items) {
            items = _safeArray(items);
            if (!items.length) return;
            lines.push('');
            lines.push('**' + title + '**');
            items.forEach(function (item) {
                var text = _safeStr(item);
                if (text) lines.push('- ' + text);
            });
        }

        pushSection('Scene Developments', payload.scene_beats);
        pushSection('World Events', payload.world_events);
        pushSection('Consequences', payload.consequences);
        pushSection('Threads', payload.threads);
        pushSection('NPC Activity', payload.npc_updates);
        pushSection('Director Activity', payload.director_activity);

        return lines.join('\n');
    }

    function isWorldAdvanceRecapPayload(payload) {
        payload = _safeObj(payload);
        if (!payload) return false;
        if (_safeStr(payload.kind) !== 'world_advance_recap') return false;

        var hasSummary = !!_safeStr(payload.summary);
        var hasMoments = Number(payload.additional_moments || 0) > 0;
        var hasSections =
            _safeArray(payload.scene_beats).length > 0 ||
            _safeArray(payload.world_events).length > 0 ||
            _safeArray(payload.consequences).length > 0 ||
            _safeArray(payload.threads).length > 0 ||
            _safeArray(payload.npc_updates).length > 0 ||
            _safeArray(payload.director_activity).length > 0;

        return hasSummary || hasMoments || hasSections;
    }

    function markRealPlayerActivity(reason) {
        window.omnix_rpg_last_activity = Date.now();
        rpgDebug('Activity', { reason: reason, at: window.omnix_rpg_last_activity });
    }

    // TTS settings
    let ttsEnabled = false;
    let narratorVoice = null;    // null = server default
    let availableVoices = [];    // populated on first use
    let currentAudioCtx = null;
    let currentAudioSource = null;

    /** Atomic state updater — increments version, merges patch. */
    function updateState(patch) {
        console.log("🔄 STATE UPDATE:", patch, "→ NEW STATE:", Object.assign({}, rpgState, patch));
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

    function buildStructuredNarrationMarkdown(update) {
        var sn = (update && update.structured_narration) || {};
        if (!sn || typeof sn !== 'object') return '';
        var parts = [];
        if (sn.scene_summary) {
            parts.push(sn.scene_summary);
        }
        if (sn.action_result_line) {
            parts.push('**Action:** ' + sn.action_result_line);
        }
        if (sn.npc_reply_block) {
            parts.push('**Reply:** ' + sn.npc_reply_block);
        }
        if (sn.rewards_block) {
            parts.push('**Reward:** ' + sn.rewards_block);
        }
        return parts.join('\n\n').trim();
    }

    function getNarrationMarkdown(update) {
        var structured = buildStructuredNarrationMarkdown(update);
        if (structured && structured.length > 0) {
            return structured;
        }
        return String((update && update.narration) || '');
    }

    function appendSystemRecapMessage(markdown) {
        if (!markdown) return;
        appendMessage({ type: 'system', content: markdown });
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
            .replace(/&/g, '&')
            .replace(/</g, '<')
            .replace(/>/g, '>')
            .replace(/"/g, '"')
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
            await fetch('/api/rpg/session/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: rpgState.sessionId,
                    voice_assignments: rpgState.voice_assignments || {},
                }),
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

    // ─── World Events panel ───────────────────────────────────────────────────

    function showWorldEventsPanel() {
        closeAllPanels();
        var panel = el('rpgWorldEventsPanel');
        if (!panel) {
            panel = document.createElement('div');
            panel.id = 'rpgWorldEventsPanel';
            panel.className = 'modal'; // Use app's modal style
            panel.innerHTML = '<div class="modal-content" id="rpgWorldEventsContent"></div>';
            document.body.appendChild(panel);
            // Close on backdrop click
            panel.addEventListener('click', function(e) {
                if (e.target === panel) panel.classList.remove('active');
            });
        }
        var content = el('rpgWorldEventsContent');
        content.innerHTML = '<div class="modal-header"><h3>World Events</h3><button class="modal-close" onclick="document.getElementById(\'rpgWorldEventsPanel\').classList.remove(\'active\');">&times;</button></div><div class="modal-body" id="rpgWorldEventsBody" style="max-height: 70vh; overflow-y: auto;"></div>';
        panel.classList.add('active');
        renderWorldEventsPanel();
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
        fetch('/api/rpg/session/list', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        }).then(r => r.json()).then(data => {
            var sessions = Array.isArray(data.sessions) ? data.sessions : [];
            if (!sessions.length) {
                loadContainer.innerHTML = '<p>No saved games</p>';
            } else {
                sessions.forEach(function(session) {
                    var manifest = session.manifest || {};
                    var item = document.createElement('div');
                    item.className = 'game-item';
                    item.innerHTML = '<span>' + (manifest.title || 'Untitled') + ' (' + (manifest.updated_at || 'Unknown') + ')</span>';
                    var loadBtn = document.createElement('button');
                    loadBtn.className = 'btn btn-secondary';
                    loadBtn.textContent = 'Load';
                    loadBtn.addEventListener('click', function() {
                        loadGame(manifest.id);
                        panel.classList.remove('active');
                    });
                    var deleteBtn = document.createElement('button');
                    deleteBtn.className = 'btn btn-danger';
                    deleteBtn.textContent = 'Delete';
                    deleteBtn.addEventListener('click', function() {
                        if (confirm('Delete this game?')) {
                            deleteGame(manifest.id);
                        }
                    });
                    item.appendChild(loadBtn);
                    item.appendChild(deleteBtn);
                    loadContainer.appendChild(item);
                });
            }
        }).catch(() => {
            loadContainer.innerHTML = '<p>Failed to load games</p>';
        });
        loadSection.appendChild(loadContainer);
        body.appendChild(loadSection);

        // Response Length Settings
        var settingsSection = document.createElement('div');
        settingsSection.innerHTML = '<h4>Response Length</h4>';
        var currentResponseLength =
            (rpgState.runtimeState &&
             rpgState.runtimeState.settings &&
             typeof rpgState.runtimeState.settings.response_length === 'string' &&
             rpgState.runtimeState.settings.response_length) || 'short';
        var responseLengthSelect = document.createElement('label');
        responseLengthSelect.innerHTML =
            'Response Length: <select id="rpgResponseLength">' +
            '<option value="short"' + (currentResponseLength === 'short' ? ' selected' : '') + '>Short</option>' +
            '<option value="medium"' + (currentResponseLength === 'medium' ? ' selected' : '') + '>Medium</option>' +
            '<option value="long"' + (currentResponseLength === 'long' ? ' selected' : '') + '>Long</option>' +
            '</select>';
        settingsSection.appendChild(responseLengthSelect);
        var saveBtn = document.createElement('button');
        saveBtn.className = 'btn btn-primary';
        saveBtn.textContent = 'Save Settings';
        saveBtn.addEventListener('click', function() {
            var responseLength = document.getElementById('rpgResponseLength').value;
            // Persist to server
            if (rpgState.sessionId) {
                fetch('/api/rpg/session/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        session_id: rpgState.sessionId,
                        settings: {
                            response_length: responseLength
                        },
                    }),
                }).then(function(response) {
                    return response.json();
                }).then(function(data) {
                    if (!data || !data.ok) {
                        alert('Failed to save settings');
                        return;
                    }
                    rpgState.runtimeState = rpgState.runtimeState || {};
                    rpgState.runtimeState.settings = data.settings || {};
                    alert('Settings saved');
                }).catch(() => {
                    alert('Failed to save settings');
                });
            } else {
                alert('No active game to save settings to');
            }
        });
        settingsSection.appendChild(document.createElement('br'));
        settingsSection.appendChild(saveBtn);
        body.appendChild(settingsSection);

        // Export and Title
        if (rpgState.sessionId) {
            var manageSection = document.createElement('div');
            manageSection.innerHTML = '<h4>Current Game</h4>';
            var exportBtn = document.createElement('button');
            exportBtn.className = 'btn btn-secondary';
            exportBtn.textContent = 'Export Game';
            exportBtn.addEventListener('click', function() {
                apiGetGame(rpgState.sessionId).then(function(game) {
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
            apiGetGame(rpgState.sessionId).then(function(game) {
                input.value = game.title || '';
            }).catch(() => {});
            var saveTitleBtn = document.createElement('button');
            saveTitleBtn.className = 'btn btn-primary';
            saveTitleBtn.textContent = 'Save Title';
            saveTitleBtn.addEventListener('click', async function() {
                try {
                    await fetch('/api/rpg/session/update', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ session_id: rpgState.sessionId, title: input.value }),
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

            // ── Phase F: In-game World Behavior settings ─────────────────
            var wbSection = document.createElement('div');
            wbSection.innerHTML = '<h4>\uD83C\uDF0D World Behavior</h4><p class="ab-hint">Adjust how the living world behaves during play.</p>';
            var wbContainer = document.createElement('div');
            wbContainer.id = 'rpgWorldBehaviorSettings';
            wbContainer.innerHTML = '<p>Loading...</p>';
            wbSection.appendChild(wbContainer);

            fetch('/api/rpg/session/world_behavior', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: rpgState.sessionId }),
            }).then(function(r) { return r.json(); }).then(function(data) {
                if (!data.ok) { wbContainer.innerHTML = '<p>Unable to load settings</p>'; return; }
                var eff = data.effective || {};
                var fields = [
                    { key: 'ambient_activity', label: 'Ambient Activity', options: ['low', 'medium', 'high'] },
                    { key: 'npc_initiative', label: 'NPC Initiative', options: ['low', 'medium', 'high'] },
                    { key: 'interruptions', label: 'Interruptions', options: ['minimal', 'normal', 'frequent'] },
                    { key: 'quest_prompting', label: 'Quest Prompting', options: ['off', 'light', 'guided', 'strong'] },
                    { key: 'companion_chatter', label: 'Companion Chatter', options: ['quiet', 'normal', 'talkative'] },
                    { key: 'world_pressure', label: 'World Pressure', options: ['gentle', 'standard', 'harsh'] },
                    { key: 'opening_guidance', label: 'Opening Guidance', options: ['light', 'normal', 'strong'] },
                    { key: 'play_style_bias', label: 'Play Style', options: ['sandbox', 'balanced', 'story_directed'] },
                ];
                var html = '';
                fields.forEach(function(f) {
                    var val = eff[f.key] || f.options[1];
                    html += '<label style="display:block;margin-bottom:6px;">' + escapeHtml(f.label) +
                        '<select class="rpg-wb-select" data-wb-key="' + f.key + '" style="margin-left:8px;">';
                    f.options.forEach(function(o) {
                        html += '<option value="' + o + '"' + (o === val ? ' selected' : '') + '>' + o.replace(/_/g, ' ') + '</option>';
                    });
                    html += '</select></label>';
                });
                html += '<button class="btn btn-primary" id="rpgSaveWorldBehavior" style="margin-top:8px;">Save World Behavior</button>';
                wbContainer.innerHTML = html;

                var saveWbBtn = wbContainer.querySelector('#rpgSaveWorldBehavior');
                if (saveWbBtn) saveWbBtn.addEventListener('click', function() {
                    var changes = {};
                    wbContainer.querySelectorAll('.rpg-wb-select').forEach(function(sel) {
                        changes[sel.getAttribute('data-wb-key')] = sel.value;
                    });
                    fetch('/api/rpg/session/world_behavior/update', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ session_id: rpgState.sessionId, changes: changes }),
                    }).then(function(r) { return r.json(); }).then(function(result) {
                        if (result.ok) { alert('World behavior updated'); }
                        else { alert('Failed to update: ' + (result.error || 'unknown')); }
                    }).catch(function() { alert('Failed to update world behavior'); });
                });
            }).catch(function() {
                wbContainer.innerHTML = '<p>Failed to load world behavior settings</p>';
            });

            body.appendChild(wbSection);
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
            startLivingWorld();
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
            await fetch('/api/rpg/session/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: gameId }),
            });
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
        var res = await fetch('/api/rpg/adventure/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) throw new Error('Failed to create game (' + res.status + ')');
        return res.json();
    }

    /**
     * Create a game via the canonical adventure start endpoint.
     */
    async function apiCreateGameStream(payload) {
        // Canonical creator start is already synchronous JSON.
        return apiCreateGame(payload || {});
    }

    async function apiGetGame(sessionId) {
        var res = await fetch('/api/rpg/session/get', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId }),
        });
        if (!res.ok) throw new Error('Failed to get game');
        var data = await res.json();
        return data.game || data;
    }

    async function apiSendTurn(sessionId, input) {
        var res = await fetch('/api/rpg/session/turn', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, input: input }),
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
            '/api/rpg/session/turn/stream',
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, input: input }),
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

    /** Send a turn with a structured action payload (non-streaming). */
    async function apiSendTurnWithAction(sessionId, input, action) {
        var res = await fetch('/api/rpg/session/turn', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, input: input, action: action }),
        });
        if (!res.ok) throw new Error('Turn request failed (' + res.status + ')');
        return res.json();
    }

    /** Send a turn with a structured action payload (streaming). */
    async function apiSendTurnStreamWithAction(sessionId, input, action, onToken) {
        var res = await fetch('/api/rpg/session/turn/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, input: input, action: action }),
        });
        if (!res.ok) throw new Error('Turn request failed (' + res.status + ')');

        var reader = res.body.getReader();
        var decoder = new TextDecoder();
        var buf = '';
        var finalData = null;

        while (true) {
            var readResult = await reader.read();
            if (readResult.done) break;
            buf += decoder.decode(readResult.value, { stream: true });

            var parts = buf.split('\n\n');
            buf = parts.pop();

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

        if (!data || typeof data !== 'object') {
            return messages;
        }

        if (isWorldAdvanceRecapPayload(data)) {
            messages.push({
                type: 'system',
                content: buildWorldAdvanceRecapMarkdown(data)
            });
        }

        _safeArray(data.resume_events).forEach(function (ev) {
            if (isWorldAdvanceRecapPayload(ev)) {
                messages.push({
                    type: 'system',
                    content: buildWorldAdvanceRecapMarkdown(ev)
                });
            }
        });

        _safeArray(data.events).forEach(function (ev) {
            if (isWorldAdvanceRecapPayload(ev)) {
                messages.push({ type: 'system', content: buildWorldAdvanceRecapMarkdown(ev) });
            }
        });

        if (data.narration) {
            messages.push({ type: 'narration', content: getNarrationMarkdown(data) });
        }
        if (Array.isArray(data.ambient_updates) && data.ambient_updates.length) {
            data.ambient_updates.forEach(function (u) {
                messages.push({ type: 'event', content: (u && u.text) ? u.text : JSON.stringify(u) });
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

    function handleResumePayload(data) {
        data = _safeObj(data);

        console.log("🔄 RESUME PAYLOAD DEBUG:", {
            hasWorldAdvanceRecap: !!data.world_advance_recap,
            hasResumeRecap: !!data.resume_recap,
            hasResumeSummary: !!data.resume_summary,
            hasRecap: !!data.recap,
            excessSummarized: data.excess_summarized,
            ticksApplied: data.ticks_applied,
            updatesCount: _safeArray(data.updates).length,
            fullData: data
        });

        var recap =
            _safeObj(data.world_advance_recap) ||
            _safeObj(data.resume_recap) ||
            _safeObj(data.resume_summary) ||
            _safeObj(data.recap);

        if (isWorldAdvanceRecapPayload(recap)) {
            console.log("📜 WORLD ADVANCE RECAP:", recap);
            appendSystemRecapMessage(buildWorldAdvanceRecapMarkdown(recap));
        } else {
            console.log("❌ NO VALID RECAP FOUND");
        }

        if (isWorldAdvanceRecapPayload(data)) {
            appendSystemRecapMessage(buildWorldAdvanceRecapMarkdown(data));
        }

        _safeArray(data.resume_events).forEach(function (ev) {
            if (isWorldAdvanceRecapPayload(ev)) {
                appendSystemRecapMessage(buildWorldAdvanceRecapMarkdown(ev));
            }
        });
    }

    function _resumeHasRecap(data) {
        data = _safeObj(data);
        if (!data) return false;
        if (isWorldAdvanceRecapPayload(data.world_advance_recap)) return true;
        if (isWorldAdvanceRecapPayload(data.resume_recap)) return true;
        if (isWorldAdvanceRecapPayload(data.resume_summary)) return true;
        if (isWorldAdvanceRecapPayload(data.recap)) return true;
        if (isWorldAdvanceRecapPayload(data)) return true;
        return _safeArray(data.resume_events).some(function (ev) {
            return isWorldAdvanceRecapPayload(ev);
        });
    }

    function onSessionLoaded(data) {
        if (!data) return;

        console.log("🎮 SESSION LOADED:", {
            sessionId: data.session_id,
            player: data.player,
            worldEvents: data.world_events,
            messagesCount: _safeArray(data.messages).length,
            memoryCount: _safeArray(data.memory).length,
            simulationState: !!data.simulation_state,
            runtimeState: !!data.runtime_state,
            fullData: data
        });

        handleResumePayload(data);

        var messages = transformResponse(data);
        messages.forEach(function (msg) {
            appendMessage(msg);
        });
    }

    function handleStreamEventPayload(payload) {
        payload = _safeObj(payload);
        if (isWorldAdvanceRecapPayload(payload)) {
            appendSystemRecapMessage(buildWorldAdvanceRecapMarkdown(payload));
            return true;
        }
        return false;
    }

    // ─── Input handler ─────────────────────────────────────────────────────────

    async function handleRPGInput(input, structuredAction) {
        if (!input || rpgState.isLoading) return;
        markRealPlayerActivity('send_turn');

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
         * Supports optional structured action payload for structured commands.
         */
        async function doSendTurn(sid) {
            var d;
            // If we have a structured action, try streaming with it
            if (structuredAction) {
                d = await apiSendTurnStreamWithAction(sid, input, structuredAction, onToken);
                if (!d) d = await apiSendTurnWithAction(sid, input, structuredAction);
            } else {
                d = await apiSendTurnStream(sid, input, onToken);
                if (!d) d = await apiSendTurn(sid, input);
            }
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
            // Render conversation cards from turn response
            if (data && data.active_conversations) {
                renderConversations(data.active_conversations);
            }
            // Speak narration after response is complete
            if (data && data.narration) speakNarration(data.narration);
        } catch (err) {
            if (streamingDiv) { streamingDiv.remove(); streamingDiv = null; }
            appendMessage({ type: 'system', content: '\u274C Error: ' + err.message });
        } finally {
            setLoading(false);
            persistSnapshot();
            if (rpgState.sessionId) startLivingWorld();
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
        console.log("💬 APPEND MESSAGE:", msg);
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
            // Handle both string choices and object choices (e.g. {text, action, data})
            var choiceText = (typeof choice === 'string') ? choice : (choice && choice.text) || JSON.stringify(choice);
            btn.textContent = choiceText;
            btn.addEventListener('click', function () {
                if (!rpgState.isLoading) {
                    // If choice is an object with an action, send it as structured action
                    if (typeof choice === 'object' && choice !== null && choice.action) {
                        handleRPGInput(choiceText, choice);
                    } else {
                        handleRPGInput(choiceText);
                    }
                }
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

            // Structured NPC action: send a human-readable input string plus a
            // canonical structured action object. This avoids echoing raw JSON
            // into narration while still giving the backend exact intent.
            card.querySelectorAll('.rpg-npc-btn').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    if (rpgState.isLoading) return;
                    var actionVerb = btn.dataset.action === 'threaten' ? 'Threaten' : 'Talk to';
                    var actionText = actionVerb + ' ' + btn.dataset.npcName;
                    var structuredAction = {
                        type: 'npc_action',
                        npc_id: btn.dataset.npcId,
                        npc_name: btn.dataset.npcName,
                        action: btn.dataset.action,
                        action_type: btn.dataset.action === 'threaten' ? 'intimidate' : 'persuade',
                        target_id: btn.dataset.npcId,
                        interaction: btn.dataset.action,
                        difficulty: 'normal'
                    };
                    handleRPGInput(actionText, structuredAction);
                });
            });

            panel.appendChild(card);
        });
    }

    function buildTurnSummaryBanner(update) {
        if (!update) return '';
        var parts = [];
        if (update.combat_result) {
            var cr = update.combat_result;
            parts.push(cr.outcome === 'hit' || cr.outcome === 'crit' ?
                '⚔️ ' + (cr.outcome || '').toUpperCase() + ': ' + (cr.damage || 0) + ' damage' :
                '🛡️ ' + (cr.outcome || 'miss').toUpperCase());
        }
        if (update.xp_result && update.xp_result.amount) {
            parts.push('✨ +' + update.xp_result.amount + ' XP');
        }
        if (update.skill_xp_result) {
            for (var skill in (update.skill_xp_result || {})) {
                if (update.skill_xp_result[skill] > 0) {
                    parts.push('📈 +' + update.skill_xp_result[skill] + ' ' + skill + ' XP');
                }
            }
        }
        if (update.level_up) {
            parts.push('🎉 Level Up! → Level ' + (update.player_level || '?'));
        }
        if (update.skill_level_ups && update.skill_level_ups.length) {
            for (var i = 0; i < update.skill_level_ups.length; i++) {
                var s = update.skill_level_ups[i];
                parts.push('📊 ' + s.skill_id + ' → Level ' + s.new_level);
            }
        }
        return parts.length > 0 ? '<div class="turn-summary-banner">' + parts.join(' | ') + '</div>' : '';
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

    function summarizeMemoryEntries(entries) {
        if (!entries || !entries.length) return [];
        return entries.slice(0, 5).map(function (e) {
            return {
                text: (e.text || '').length > 80 ? (e.text || '').substring(0, 77) + '...' : (e.text || ''),
                strength: e.strength || 0,
                source: e.source || '',
            };
        });
    }

    function dedupeMemoryEntries(entries) {
        if (!entries || !entries.length) return [];
        var seen = {};
        return entries.filter(function (e) {
            var key = e.text || '';
            if (seen[key]) return false;
            seen[key] = true;
            return true;
        });
    }

    function toggleMemoryPanel() {
        var panel = el('rpgMemoryPanelWrapper');
        if (panel) {
            panel.classList.toggle('collapsed');
        }
    }

    /** Safely convert a memory/event value to a display string. */
    function _toDisplayString(val) {
        if (val === null || val === undefined) return '';
        if (typeof val === 'string') return val;
        // If it's an object, try common text fields
        if (typeof val === 'object') {
            return val.text || val.description || val.summary || val.content || JSON.stringify(val);
        }
        return String(val);
    }

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
            // Show last 5 memory entries — handle both strings and objects
            memList.innerHTML = rpgState.memory.slice(-5).map(function (m) {
                return '<li class="rpg-memory-item">' + escapeHtml(_toDisplayString(m)) + '</li>';
            }).join('');
        }

        if (eventsList && hasEvents) {
            // Show last 5 world events — handle both strings and objects
            eventsList.innerHTML = rpgState.worldEvents.slice(-5).map(function (e) {
                return '<li class="rpg-memory-item rpg-memory-item--event">' + escapeHtml(_toDisplayString(e)) + '</li>';
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
            skillHtml =
                '<div class="rpg-player-section-title">🎯 Skills</div>' +
                '<div class="rpg-player-skills">' +
                skillKeys.map(function(sk) {
                    var entry = (skills[sk] && typeof skills[sk] === 'object') ? skills[sk] : { level: Number(skills[sk] || 0), xp: 0, xp_to_next: 25 };
                    var lvl = Number(entry.level || 0);
                    var xp = Number(entry.xp || 0);
                    var xpToNext = Number(entry.xp_to_next || 25);
                    var pct = xpToNext > 0 ? Math.max(0, Math.min(100, Math.floor((xp / xpToNext) * 100))) : 0;

                    return '' +
                        '<div class="rpg-skill-card">' +
                            '<div class="rpg-skill-header">' +
                                '<span class="rpg-skill-name">' + escapeHtml(sk) + '</span>' +
                                '<span class="rpg-skill-level">Lv ' + lvl + '</span>' +
                            '</div>' +
                            '<div class="rpg-skill-meta">' + xp + ' / ' + xpToNext + ' XP</div>' +
                            '<div class="rpg-skill-progress"><div class="rpg-skill-progress-fill" style="width:' + pct + '%"></div></div>' +
                        '</div>';
                }).join('') +
                '</div>';
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
            fetch('/api/rpg/session/get', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: rpgState.sessionId }),
            })
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

            var worldEventsBtn = el('rpgWorldEventsBtn');
            if (worldEventsBtn) worldEventsBtn.addEventListener('click', showWorldEventsPanel);

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
        console.warn('[RPG] Legacy showSetupModal() invoked; redirecting to Adventure Builder');
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
        // Stop living-world heartbeat/stream
        stopAmbientHeartbeat();
        disconnectSessionStream();
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
            ambientSeq:  0,
            unreadAmbient: 0,
            ambientFeedBuffer: [],
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

    // ─── Living World: Ambient Feed + Subscription (Phases 8-10) ────────────────

    var HEARTBEAT_INTERVAL_MS = 5000; // 5 seconds
    var AMBIENT_RECONNECT_DELAY_MS = 3000;
    var _ambientReconnectAttempts = 0;
    var _maxReconnectAttempts = 10;

    // ── Phase 8: Persistent SSE subscription ─────────────────────────────────

    function connectSessionStream() {
        if (!rpgState.sessionId) return;
        disconnectSessionStream();

        var url = '/api/rpg/session/stream?session_id=' +
            encodeURIComponent(rpgState.sessionId) +
            '&after_seq=' + (rpgState.ambientSeq || 0);

        try {
            var es = new EventSource(url);
            updateState({ sessionStream: es });

            es.onmessage = function (event) {
                try {
                    var data = JSON.parse(event.data);
                    if (handleStreamEventPayload(data)) {
                        return;
                    }
                    rpgDebug('SSE:Message', data);
                    if (data.type === 'ambient' && data.update) {
                        rpgDebug('Ambient:SSE', data.update);
                        handleAmbientUpdate(data.update);
                    } else if (data.type === 'heartbeat') {
                        var serverSeq = parseInt(data.latest_seq, 10) || 0;
                        if (serverSeq > rpgState.ambientSeq) {
                            pollAmbientUpdates();
                        }
                    }
                } catch (e) { rpgDebug('SSE:ParseError', e); }
            };

            es.onerror = function () {
                rpgDebug('SSE:Error', { attempts: _ambientReconnectAttempts });
                disconnectSessionStream();
                _ambientReconnectAttempts++;
                if (_ambientReconnectAttempts < _maxReconnectAttempts) {
                    setTimeout(connectSessionStream, AMBIENT_RECONNECT_DELAY_MS * _ambientReconnectAttempts);
                }
            };

            es.onopen = function () {
                rpgDebug('SSE:Open', { sessionId: rpgState.sessionId });
                _ambientReconnectAttempts = 0;
            };

            es.addEventListener('resume_recap', function (event) {
                var payload = JSON.parse(event.data);
                if (handleStreamEventPayload(payload)) {
                    return;
                }
            });

            es.addEventListener('world_advance_recap', function (event) {
                var payload = JSON.parse(event.data);
                if (handleStreamEventPayload(payload)) {
                    return;
                }
            });
        } catch (e) {
            // SSE not supported — fall back to polling
            startAmbientPolling();
        }
    }

    function disconnectSessionStream() {
        if (rpgState.sessionStream) {
            try { rpgState.sessionStream.close(); } catch (e) { /* ignore */ }
            updateState({ sessionStream: null });
        }
    }

    // ── Phase 8: Heartbeat idle advancement ──────────────────────────────────

    function startAmbientHeartbeat() {
        stopAmbientHeartbeat();
        if (!rpgState.sessionId) return;

        rpgState.heartbeatTimer = setInterval(function () {
            if (!rpgState.sessionId) { stopAmbientHeartbeat(); return; }
            if (document.hidden) return; // Don't tick when tab is hidden
            // Do NOT update last_activity here — only real player actions should

            rpgDebug('IdleTick:Request', { sessionId: rpgState.sessionId, reason: 'heartbeat' });

            fetch('/api/rpg/session/idle_tick', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: rpgState.sessionId,
                    count: 1,
                    reason: 'heartbeat',
                }),
            }).then(function (r) { return r.json(); })
              .then(function (data) {
                rpgDebug('IdleTick:Response', data);
                if (data.ok && data.updates && data.updates.length) {
                    data.updates.forEach(function (u) { handleAmbientUpdate(u); });
                }
                // Update settings from server echo
                if (data.settings) {
                    updateState({ settings: data.settings });
                }

                // 🔥 CRITICAL: refresh world events after each tick
                fetchWorldEvents();
            }).catch(function (err) {
                rpgDebug('IdleTick:Error', err);
            });
        }, HEARTBEAT_INTERVAL_MS);
    }

    function stopAmbientHeartbeat() {
        if (rpgState.heartbeatTimer) {
            clearInterval(rpgState.heartbeatTimer);
            rpgState.heartbeatTimer = null;
        }
    }

    // ── Phase 8: Poll fallback ───────────────────────────────────────────────

    function startAmbientPolling() {
        stopAmbientPolling();
        if (!rpgState.sessionId) return;

        rpgState.pollTimer = setInterval(function () {
            if (!rpgState.sessionId) { stopAmbientPolling(); return; }
            if (document.hidden) return;
            pollAmbientUpdates();
        }, HEARTBEAT_INTERVAL_MS + 1000);
    }

    function stopAmbientPolling() {
        if (rpgState.pollTimer) {
            clearInterval(rpgState.pollTimer);
            rpgState.pollTimer = null;
        }
    }

    function pollAmbientUpdates() {
        if (!rpgState.sessionId) return;
        fetch('/api/rpg/session/poll', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: rpgState.sessionId,
                after_seq: rpgState.ambientSeq || 0,
                limit: 8,
            }),
        }).then(function (r) { return r.json(); })
          .then(function (data) {
            if (data.ok && data.updates && data.updates.length) {
                console.log("🌍 POLLED AMBIENT UPDATES:", data.updates.length, data.updates);
                data.updates.forEach(function (u) { handleAmbientUpdate(u); });
            } else {
                console.log("🌍 NO NEW AMBIENT UPDATES");
            }
        }).catch(function () { /* ignore poll failures */ });
    }

    // ── Phase 9: Ambient update handling and rendering ───────────────────────

    function handleAmbientUpdate(update) {
        if (!update) return;
        var seq = parseInt(update.seq, 10) || 0;
        // Dedup: skip if already seen
        if (seq <= rpgState.ambientSeq) return;
        updateState({ ambientSeq: seq });

        rpgDebug('Ambient:Decision', {
            seq: seq,
            kind: update.kind,
            delivery: update.delivery,
            isTyping: rpgState.isTyping,
            is_reaction: update.is_reaction,
            is_idle_conversation: update.is_idle_conversation,
        });

        // Handle scene weaver beats
        if (update.source === 'scene_weaver') {
            appendSceneBeat(update);
            return;
        }

        var kind = update.kind || 'world_event';
        var isUrgent = kind === 'combat_start' || kind === 'warning' ||
            kind === 'demand' || kind === 'plea_for_help' ||
            (kind === 'npc_to_player' && update.interrupt) ||
            (kind === 'taunt' && update.interrupt) ||
            (kind === 'quest_prompt' && update.interrupt);

        // Idle chatter should stay visible in the feed even while the input is focused.
        // Only buffer non-idle ambient updates while the user is actively typing.
        var isIdleConversation =
            !!update.is_idle_conversation ||
            update.lane === 'idle' ||
            (update.structured && update.structured.lane === 'idle') ||
            kind === 'idle_check_in' ||
            kind === 'gossip' ||
            kind === 'npc_to_npc';

        if (rpgState.isTyping && !isUrgent && !isIdleConversation) {
            // Queue as unread
            rpgState.ambientFeedBuffer.push(update);
            updateState({ unreadAmbient: rpgState.unreadAmbient + 1 });
            updateUnreadBadge();
            return;
        }

        // Idle NPC chatter renders immediately.
        appendAmbientUpdate(update);
    }

    function appendSceneBeat(update) {
        const feed = el('rpgAmbientFeed') || el('rpgNarrativeFeed') || el('chatMessages');
        if (!feed) return;

        const sceneId = update.structured?.scene_id;
        if (!sceneId) return appendAmbientUpdate(update);
        const sceneKind = (update.structured?.scene_kind || 'scene').replace(/_/g, ' ');

        let container = feed.querySelector(`[data-scene-id="${sceneId}"]`);

        if (!container) {
            container = document.createElement('div');
            container.className = 'rpg-ambient rpg-ambient-scene';
            container.dataset.sceneId = sceneId;
            container.dataset.sceneKind = sceneKind;
            container.dataset.lastBeatTs = String(Date.now());
            container.dataset.beatCount = '0';

            container.innerHTML = `
                <div class="rpg-ambient-scene-header">${escapeHtml(sceneKind)}</div>
                <div class="rpg-ambient-scene-lines"></div>
            `;

            feed.appendChild(container);
        }
        container.dataset.lastBeatTs = String(Date.now());
        container.dataset.beatCount = String((parseInt(container.dataset.beatCount || '0', 10) || 0) + 1);
        container.classList.remove('rpg-ambient-scene-faded');

        const lines = container.querySelector('.rpg-ambient-scene-lines');

        const row = document.createElement('div');
        row.className = 'rpg-ambient-scene-line';
        if (update.target_id === 'player') {
            row.classList.add('rpg-ambient-scene-line--to-player');
        }
        if (update.kind === 'npc_to_npc') {
            row.classList.add('rpg-ambient-scene-line--npc-to-npc');
        }
        if (update.kind === 'npc_to_player') {
            row.classList.add('rpg-ambient-scene-line--npc-to-player');
        }
        if (
            update.kind === 'companion_comment' ||
            (update.speaker_id && String(update.speaker_id).toLowerCase().indexOf('companion') !== -1)
        ) {
            row.classList.add('rpg-ambient-scene-line--companion');
        }

        row.innerHTML = `
            <span class="rpg-ambient-scene-speaker">${escapeHtml(update.speaker_name || 'NPC')}</span>
            <span class="rpg-ambient-scene-text">${escapeHtml(update.text || '')}</span>
        `;

        lines.appendChild(row);

        // Lightweight fade marker for old scenes so the feed stays readable.
        window.clearTimeout(container._fadeTimer);
        container._fadeTimer = window.setTimeout(function () {
            container.classList.add('rpg-ambient-scene-faded');
        }, 8000);

        window.clearTimeout(container._removeTimer);
        container._removeTimer = window.setTimeout(function () {
            var lastBeatTs = parseInt(container.dataset.lastBeatTs || '0', 10) || 0;
            if ((Date.now() - lastBeatTs) < 12000) return;
            if (container && container.parentNode) {
                container.parentNode.removeChild(container);
            }
        }, 20000);
    }

    function appendAmbientUpdate(update) {
        console.log("🌍 AMBIENT UPDATE:", update);
        var feed = el('rpgNarrativeFeed');
        if (!feed) return;

        var welcome = el('rpgWelcome');
        if (welcome) welcome.style.display = 'none';

        var card = renderAmbientCard(update);
        feed.appendChild(card);
        feed.scrollTop = feed.scrollHeight;

        // TTS for NPC speech
        if (ttsEnabled && update.speaker_name && update.text) {
            speakText(update.text, update.speaker_name);
        }
    }

    // ── Phase 9: Ambient card renderer ───────────────────────────────────────

    function renderAmbientCard(update) {
        var div = document.createElement('div');
        var kind = update.kind || 'world_event';

        // Map kind → CSS class
        var kindClass = 'rpg-ambient--' + kind.replace(/_/g, '-');
        div.className = 'rpg-msg rpg-ambient ' + kindClass;

        var content = '';
        switch (kind) {
            case 'npc_to_player':
                content = '<span class="rpg-ambient-speaker">' + escapeHtml(update.speaker_name || 'NPC') + '</span> '
                    + '<span class="rpg-ambient-says">says to you:</span> '
                    + '<em class="rpg-ambient-text">"' + escapeHtml(update.text || '') + '"</em>';
                break;
            case 'npc_to_npc':
                content = '<span class="rpg-ambient-speaker">' + escapeHtml(update.speaker_name || 'NPC') + '</span> '
                    + '<span class="rpg-ambient-says">speaks to '
                    + escapeHtml(update.target_name || 'someone') + ':</span> '
                    + '<em class="rpg-ambient-text">"' + escapeHtml(update.text || '') + '"</em>';
                break;
            case 'arrival':
                content = '\uD83D\uDEB6 <span class="rpg-ambient-text">' + escapeHtml(update.text || 'Someone arrives.') + '</span>';
                break;
            case 'departure':
                content = '\uD83D\uDEB6 <span class="rpg-ambient-text">' + escapeHtml(update.text || 'Someone departs.') + '</span>';
                break;
            case 'combat_start':
                content = '\u2694\uFE0F <strong class="rpg-ambient-text rpg-ambient-urgent">'
                    + escapeHtml(update.text || 'Combat begins!') + '</strong>';
                break;
            case 'warning':
                content = '\u26A0\uFE0F <span class="rpg-ambient-speaker">' + escapeHtml(update.speaker_name || '') + '</span> '
                    + '<span class="rpg-ambient-text rpg-ambient-urgent">' + escapeHtml(update.text || 'Be careful!') + '</span>';
                break;
            case 'companion_comment':
                content = '\uD83D\uDCAC <span class="rpg-ambient-speaker">' + escapeHtml(update.speaker_name || 'Companion') + '</span>: '
                    + '<em class="rpg-ambient-text">"' + escapeHtml(update.text || '') + '"</em>';
                break;
            case 'quest_prompt':
                content = '\uD83D\uDCDC <span class="rpg-ambient-speaker">' + escapeHtml(update.speaker_name || 'NPC') + '</span> '
                    + '<span class="rpg-ambient-text rpg-ambient-quest">' + escapeHtml(update.text || 'A new quest beckons.') + '</span>';
                break;
            case 'recruitment_offer':
                content = '\uD83E\uDD1D <span class="rpg-ambient-speaker">' + escapeHtml(update.speaker_name || 'NPC') + '</span> '
                    + '<span class="rpg-ambient-text">' + escapeHtml(update.text || 'An offer is made.') + '</span>';
                break;
            case 'plea_for_help':
                content = '\uD83C\uDD98 <span class="rpg-ambient-speaker">' + escapeHtml(update.speaker_name || 'NPC') + '</span> '
                    + '<span class="rpg-ambient-text rpg-ambient-urgent">' + escapeHtml(update.text || 'Someone needs your help!') + '</span>';
                break;
            case 'demand':
                content = '\u2757 <span class="rpg-ambient-speaker">' + escapeHtml(update.speaker_name || 'NPC') + '</span> '
                    + '<span class="rpg-ambient-text rpg-ambient-urgent">' + escapeHtml(update.text || 'A demand is made.') + '</span>';
                break;
            case 'taunt':
                content = '\uD83D\uDE24 <span class="rpg-ambient-speaker">' + escapeHtml(update.speaker_name || 'NPC') + '</span> '
                    + '<span class="rpg-ambient-text">' + escapeHtml(update.text || 'Someone taunts you.') + '</span>';
                break;
            case 'follow_reaction':
                content = '\uD83C\uDFC3 <span class="rpg-ambient-speaker">' + escapeHtml(update.speaker_name || 'NPC') + '</span> '
                    + '<span class="rpg-ambient-text">' + escapeHtml(update.text || 'Someone hurries after you.') + '</span>';
                break;
            case 'caution_reaction':
                content = '\u26A0\uFE0F <span class="rpg-ambient-speaker">' + escapeHtml(update.speaker_name || 'NPC') + '</span> '
                    + '<span class="rpg-ambient-text rpg-ambient-urgent">' + escapeHtml(update.text || 'Someone urges caution.') + '</span>';
                break;
            case 'assist_reaction':
                content = '\uD83E\uDD1D <span class="rpg-ambient-speaker">' + escapeHtml(update.speaker_name || 'NPC') + '</span> '
                    + '<span class="rpg-ambient-text">' + escapeHtml(update.text || 'Someone moves to assist you.') + '</span>';
                break;
            case 'idle_check_in':
                content = '\uD83D\uDCAC <span class="rpg-ambient-speaker">' + escapeHtml(update.speaker_name || 'Companion') + '</span>: '
                    + '<em class="rpg-ambient-text">"' + escapeHtml(update.text || '') + '"</em>';
                break;
            case 'gossip':
                content = '\uD83D\uDDE3\uFE0F <span class="rpg-ambient-speaker">' + escapeHtml(update.speaker_name || 'NPC') + '</span>: '
                    + '<em class="rpg-ambient-text rpg-ambient-gossip">"' + escapeHtml(update.text || '') + '"</em>';
                break;
            case 'system_summary':
                content = '\uD83D\uDCDC <span class="rpg-ambient-text rpg-ambient-summary">' + escapeHtml(update.text || '') + '</span>';
                break;
            default:
                content = '\uD83C\uDF0D <span class="rpg-ambient-text">' + escapeHtml(update.text || 'The world stirs.') + '</span>';
                break;
        }

        div.innerHTML = content;

        // Add subtle timestamp
        var time = document.createElement('span');
        time.className = 'rpg-ambient-time';
        time.textContent = 'tick ' + (update.tick || '?');
        div.appendChild(time);

        return div;
    }

    // ── Phase 9: Unread badge and typing-aware flush ─────────────────────────

    function updateUnreadBadge() {
        var badge = el('rpgAmbientBadge');
        if (!badge) return;
        if (rpgState.unreadAmbient > 0) {
            badge.textContent = rpgState.unreadAmbient;
            badge.style.display = 'inline-block';
        } else {
            badge.style.display = 'none';
        }
    }

    function flushAmbientBuffer() {
        if (!rpgState.ambientFeedBuffer.length) return;
        var buffer = rpgState.ambientFeedBuffer.slice();
        rpgState.ambientFeedBuffer = [];
        updateState({ unreadAmbient: 0 });
        updateUnreadBadge();
        buffer.forEach(function (u) { appendAmbientUpdate(u); });
    }

    // ── World Events Panel ───────────────────────────────────────────────────

    function _adaptPlayerWorldViewRowForPanel(row) {
        row = _safeObj(row);

        var actors = _safeArray(row.actors).filter(Boolean);
        var actorLabel = _safeStr(row.actor_label || '');
        var title = actorLabel || _safeStr(row.title || 'Event');
        var summary = _safeStr(row.summary || '');
        var tick = Number(row.tick || 0);
        var locationId = _safeStr(row.location_id || '');
        var locationLabel = _getLocationDisplayName(locationId);
        var kind = _safeStr(row.kind || 'event');
        var scope = _safeStr(row.scope || 'local');
        var priority = Number(row.priority || 0);
        var status = _safeStr(row.status || 'active');
        var source = _safeStr(row.source || '');

        // For world_view_activity, ensure title is actor-focused
        if (kind === 'world_view_activity') {
            if (actorLabel && summary.startsWith(actorLabel + ' ')) {
                summary = summary.substring(actorLabel.length + 1);
            }
        }

        // For merged activity rows, trim leading repeated actor label more aggressively
        if (kind === 'world_view_activity' && actorLabel) {
            var loweredSummary = summary.toLowerCase();
            var loweredActor = actorLabel.toLowerCase();
            if (loweredSummary.indexOf(loweredActor + ' ') === 0) {
                summary = summary.substring(actorLabel.length + 1);
                if (summary.length) {
                    summary = summary.charAt(0).toUpperCase() + summary.slice(1);
                }
            }
        }

        var displayTitle = title;
        if (kind === 'world_view_consequence') {
            displayTitle = _safeStr(row.title || 'World Consequence');
        }

        var subtitle = locationLabel || '';
        if (kind === 'world_view_activity') {
            subtitle = locationLabel || '';
        }
        if (kind === 'world_view_consequence') {
            subtitle = locationLabel || '';
        }

        // Hide technical sources
        var displaySource = '';

        return {
            event_id: _safeStr(row.event_id || ''),
            scope: scope,
            kind: kind,
            title: displayTitle,
            summary: summary,
            subtitle: subtitle,
            tick: tick,
            tick_label: tick > 0 ? ('Tick ' + tick) : '',
            actors: actors,
            actor_text: actorLabel,
            location_id: locationId,
            priority: priority,
            priority_label: priority > 0 ? String(priority) : '',
            status: status,
            source: displaySource,
            chips: [],
        };

    }

    function _getLocationDisplayName(locationId) {
        // Placeholder for location label mapping
        if (!locationId) return '';
        var mapping = {
            'loc_tavern': 'Tavern',
            'loc_town_square': 'Town Square',
            // Add more as needed
        };
        return mapping[locationId] || locationId.replace('loc_', '').replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }

    function _groupPlayerWorldViewRows(rows) {
        rows = _safeArray(rows);
        var grouped = {
            local_events: [],
            global_events: [],
            director_pressure: [],
            recent_changes: [],
        };

        rows.forEach(function (rawRow) {
            var row = _adaptPlayerWorldViewRowForPanel(rawRow);
            grouped.recent_changes.push(row);

            if (row.scope === 'director') {
                grouped.director_pressure.push(row);
            } else if (row.scope === 'global') {
                grouped.global_events.push(row);
            } else {
                grouped.local_events.push(row);
            }
        });

        return grouped;
    }

    function fetchWorldEvents() {
        if (!rpgState.sessionId) return;
        fetch('/api/rpg/session/world_events', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: rpgState.sessionId,
            }),
        }).then(function (r) { return r.json(); })
          .then(function (data) {
            console.log("DEBUG FRONTEND RECEIVED world_events", data);
            console.log('DEBUG fetchWorldEvents response', data);
            console.log(
                'DEBUG fetchWorldEvents rows',
                Array.isArray(data && data.recent_world_event_rows) ? data.recent_world_event_rows : []
            );
            rpgDebug('WorldEvents:Response', data);
            if (data.ok) {
                var rawRows = _safeArray(data.recent_world_event_rows);
                var playerRows = _safeArray(data.player_world_view_rows);
                var playerLocalRows = _safeArray(data.player_local_world_view_rows);
                var playerGlobalRows = _safeArray(data.player_global_world_view_rows);
                updateState({
                    worldEventsSummary: {
                        recent_world_event_rows: rawRows,
                        player_world_view_rows: playerRows,
                        player_local_world_view_rows: playerLocalRows,
                        player_global_world_view_rows: playerGlobalRows,
                    },
                    worldEventsView: {
                        local_events: _groupPlayerWorldViewRows(playerLocalRows).local_events,
                        global_events: _groupPlayerWorldViewRows(playerGlobalRows).global_events,
                        director_pressure: [],
                        recent_changes: playerRows,
                    },
                    worldEventsTab: rpgState.worldEventsTab || 'local',
                });
                if (el('rpgWorldEventsBody')) renderWorldEventsPanel();
            }
        }).catch(function (err) {
            rpgDebug('WorldEvents:Error', err);
        });
    }

    function setWorldEventsTab(tab) {
        updateState({ worldEventsTab: tab === 'global' ? 'global' : 'local' });
        renderWorldEventsPanel();
        return false;
    }

    function renderWorldEventsPanel() {
        console.log("DEBUG renderWorldEventsPanel CALLED");
        console.log("DEBUG RENDER INPUT", {
            view: rpgState.worldEventsView,
            summary: rpgState.worldEventsSummary
        });
        console.log('DEBUG renderWorldEventsPanel start', {
            worldEventsView: rpgState.worldEventsView,
            worldEventsSummary: rpgState.worldEventsSummary
        });
        const panel = el('rpgWorldEventsBody');

        console.log('DEBUG panel lookup', panel);

        if (!panel) return; // Modal not open

        var view = _safeObj(rpgState.worldEventsView);
        var summary = _safeObj(rpgState.worldEventsSummary);
        if ((!view.local_events && !view.global_events && !view.director_pressure) &&
            _safeArray(summary.player_world_view_rows).length) {
            view = _groupPlayerWorldViewRows(summary.player_world_view_rows);
        }

        var localEvents = _safeArray(view.local_events);
        var globalEvents = _safeArray(view.global_events);
        var directorPressure = _safeArray(view.director_pressure);

        console.log('DEBUG renderWorldEventsPanel arrays', {
            localCount: localEvents.length,
            globalCount: globalEvents.length,
            directorCount: directorPressure.length,
        });

        console.log('DEBUG renderWorldEventsPanel sample local', localEvents.slice(0, 2));

        console.log('DEBUG renderWorldEventsPanel panel before', panel);

        var activeTab = _safeStr(rpgState.worldEventsTab || 'local');
        var visibleRows = activeTab === 'global' ? globalEvents : localEvents;

        var html = '<div class="rpg-we-tabs">'
            + '<button class="rpg-we-tab' + (activeTab === 'local' ? ' is-active' : '') + '" onclick="return window.setWorldEventsTab && window.setWorldEventsTab(\'local\')">Local</button>'
            + '<button class="rpg-we-tab' + (activeTab === 'global' ? ' is-active' : '') + '" onclick="return window.setWorldEventsTab && window.setWorldEventsTab(\'global\')">Global</button>'
            + '</div>';

        console.log('DEBUG renderWorldEventsPanel html before assign', html);

        if (visibleRows.length) {
            visibleRows.forEach(function (row) {
                html += _renderWorldEventCard(row);
            });
        } else {
            html += '<p class="rpg-we-empty">No world events yet.</p>';
        }

        if (!html) {
            html = '<p class="rpg-we-empty">No world events yet.</p>';
        }

        console.log('DEBUG renderWorldEventsPanel html_length', html.length);
        console.log('DEBUG renderWorldEventsPanel panel_element', panel);

        panel.innerHTML = html;

        console.log('DEBUG renderWorldEventsPanel panel after', panel.innerHTML);

        setTimeout(() => {
            console.log('DEBUG panel after 100ms', panel.innerHTML);
        }, 100);

        console.log('DEBUG renderWorldEventsPanel final_dom', panel.innerHTML);

        console.log('DEBUG panel computed style', getComputedStyle(panel));
    }

    function _renderWorldEventCard(row) {
        var title = escapeHtml(row.title || 'Event');
        var summary = escapeHtml(row.summary || '');
        var tickLabel = escapeHtml(row.tick_label || 'Tick ?');
        var status = escapeHtml(row.status || '');
        var source = escapeHtml(row.source || '');
        var actors = escapeHtml(row.actor_text || '');

        return '<div style="border:1px solid #555; border-radius:4px; padding:12px; margin:8px 0; background:#333; color:#fff;">'
            + '<div style="font-weight:bold; margin-bottom:4px; color:#fff;">' + title + '</div>'
            + '<div style="margin-bottom:4px; color:#ccc;">' + summary + '</div>'
            + '<div style="font-size:0.9em; color:#888;">' + tickLabel
            + (status ? ' | ' + status : '')
            + (source ? ' | ' + source : '')
            + (actors ? ' | ' + actors : '') + '</div>'
            + '</div>';
    }

    // ── Phase 10: Typing detection for ambient flow ──────────────────────────

    function _setupTypingDetection() {
        var inputEl = el('userInput') || el('chatInput');
        if (!inputEl) return;

        function clearTypingSoon() {
            window.clearTimeout(typingIdleTimer);
            typingIdleTimer = window.setTimeout(function () {
                updateState({ isTyping: false });
                flushAmbientBuffer();
            }, TYPING_IDLE_MS);
        }

        inputEl.addEventListener('focus', function () {
            updateState({ isTyping: true });
            markRealPlayerActivity('input_focus');
            clearTypingSoon();
        });
        inputEl.addEventListener('blur', function () {
            window.clearTimeout(typingIdleTimer);
            updateState({ isTyping: false });
            flushAmbientBuffer();
        });
        inputEl.addEventListener('input', function () {
            updateState({ isTyping: true });
            markRealPlayerActivity('input_typing');
            clearTypingSoon();
        });
        inputEl.addEventListener('keydown', function () {
            updateState({ isTyping: true });
            clearTypingSoon();
        });
        inputEl.addEventListener('paste', function () {
            updateState({ isTyping: true });
            clearTypingSoon();
        });
    }

    // ── Phase 8: Bootstrap living world on session load ──────────────────────

    function startLivingWorld() {
        if (!rpgState.sessionId) return;
        console.log("🌍 STARTING LIVING WORLD for session:", rpgState.sessionId);
        // Resume catch-up: compute elapsed seconds since last activity
        var lastActivity = parseInt(localStorage.getItem('omnix_rpg_last_activity') || '0', 10);
        var now = Date.now();
        var elapsedSeconds = lastActivity ? Math.floor((now - lastActivity) / 1000) : 0;

        // Record current activity time
        localStorage.setItem('omnix_rpg_last_activity', String(now));

        if (elapsedSeconds > 10) {
            fetch('/api/rpg/session/resume', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: rpgState.sessionId,
                    elapsed_seconds: elapsedSeconds,
                }),
            }).then(function (r) { return r.json(); })
              .then(function (data) {
                console.log("RESUME RESPONSE", data);
                console.log("RESUME RECAP", data && data.world_advance_recap);
                if (data.ok) {
                    handleResumePayload(data);

                    var hasRecap = _resumeHasRecap(data);
                    var updates = _safeArray(data.updates);

                    if (hasRecap) {
                        updates = updates.filter(function (u) {
                            return _safeStr(_safeObj(u).kind) !== 'system_summary';
                        });
                    }

                    updates.forEach(function (u) { appendAmbientUpdate(u); });
                    updateState({ ambientSeq: data.latest_seq || rpgState.ambientSeq });
                }
            }).catch(function () { /* ignore resume errors */ });
        }

        startAmbientHeartbeat();
        connectSessionStream();
        _setupTypingDetection();
        console.log('[RPG] Living world started (session=' + rpgState.sessionId + ', seq=' + rpgState.ambientSeq + ')');
    }

    function stopLivingWorld() {
        stopAmbientHeartbeat();
        stopAmbientPolling();
        disconnectSessionStream();
    }

    // ─── Init ──────────────────────────────────────────────────────────────────

    function init() {
        console.log('[RPG] Initializing RPG mode\u2026');

        window._currentMode = 'chat';

        // ── Adventure Builder launch callback ──────────────────────────────
        // When the builder successfully launches an adventure, pipe the
        // result into the RPG feed just like legacy game creation.
        window._onAdventureBuilderLaunch = function (res) {
            if (!res || !res.session_id) {
                console.error('[RPG] Adventure Builder launch returned invalid payload', res);
                alert('Failed to launch adventure: invalid session payload.');
                return;
            }

            updateState({ sessionId: res.session_id });
            localStorage.setItem(STORAGE_KEY, rpgState.sessionId);
            localStorage.setItem('omnix_rpg_last_creator_launch', JSON.stringify({
                session_id: res.session_id,
                response_version: res.response_version || 1,
                created_at: Date.now()
            }));

            updateState({
                world: res.world || {},
                player: res.player || {},
                locations: res.locations || [],
                factions: res.factions || [],
                npcs: res.npcs || [],
                settings: res.settings || rpgState.settings || {},
                worldEventsSummary: res.world_events_summary || {},
            });

            if (res.opening && res.opening.trim()) {
                applyUpdate(transformResponse({ narration: res.opening }));
            }

            if (typeof renderWorld === 'function') renderWorld();
            if (typeof renderPlayer === 'function') renderPlayer();
            renderNPCs();

            if (res.memory && res.memory.length) {
                updateState({ memory: res.memory });
            }
            if (res.worldEvents && res.worldEvents.length) {
                updateState({ worldEvents: res.worldEvents });
            }
            persistSnapshot();
            startLivingWorld();
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

        // Start living-world subscription if session exists
        if (rpgState.sessionId) {
            startLivingWorld();
        }

        console.log('[RPG] RPG mode ready (state v' + stateVersion + ')');
    }

    // ── Conversation rendering ────────────────────────────────────────────

    function renderConversations(conversations) {
        var root = document.getElementById("rpg-conversations");
        if (!root) return;
        root.innerHTML = "";

        (conversations || []).forEach(function(conv) {
            var card = document.createElement("div");
            card.className = "rpg-conversation-card";

            var title = document.createElement("div");
            title.className = "rpg-conversation-title";
            var topic = (conv.topic && conv.topic.summary) || "Conversation";
            title.textContent = topic;
            card.appendChild(title);

            var body = document.createElement("div");
            body.className = "rpg-conversation-lines";
            (conv.lines || []).slice(-4).forEach(function(line) {
                var row = document.createElement("div");
                row.className = "rpg-conversation-line";
                var speaker = line.speaker_name || line.speaker || "Someone";
                row.textContent = speaker + ': "' + (line.text || "") + '"';
                body.appendChild(row);
            });
            card.appendChild(body);

            if (conv.player_can_intervene && (conv.intervention_options || []).length) {
                var actions = document.createElement("div");
                actions.className = "rpg-conversation-actions";
                conv.intervention_options.forEach(function(opt) {
                    var btn = document.createElement("button");
                    btn.className = "rpg-choice-btn";
                    btn.textContent = opt.text || opt.id;
                    btn.onclick = function() { sendConversationIntervention(conv.conversation_id, opt.id); };
                    actions.appendChild(btn);
                });
                card.appendChild(actions);
            }

            root.appendChild(card);
        });
    }

    function sendConversationIntervention(conversationId, optionId) {
        var payload = {
            session_id: rpgState.sessionId,
            conversation_id: conversationId,
            option_id: optionId,
        };
        fetch("/api/rpg/session/conversation/intervene", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload),
        })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data && data.active_conversations) {
                renderConversations(data.active_conversations);
            }
        })
        .catch(function(err) {
            console.error('[RPG] Conversation intervention error:', err);
        });
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
        // Living-world debug helpers
        startLivingWorld: startLivingWorld,
        stopLivingWorld:  stopLivingWorld,
        flushAmbient:     flushAmbientBuffer,
        pollAmbient:      pollAmbientUpdates,
        // World events tab helper
        setWorldEventsTab: setWorldEventsTab,
        // Debug logging
        debugDump: function() {
            console.group("🎮 RPG DEBUG DUMP");
            console.log("📊 STATE:", rpgState);
            console.log("💬 MESSAGES:", rpgState.messages);
            console.log("🌍 WORLD EVENTS:", rpgState.worldEvents);
            console.log("🧠 MEMORY:", rpgState.memory);
            console.log("🎲 ROLLS:", rpgState.rolls);
            console.log("⚙️  SETTINGS:", rpgState.settings);
            console.log("👤 PLAYER:", rpgState.player);
            console.groupEnd();
            return rpgState;
        }
    };

    if (typeof window !== 'undefined') {
        window.setWorldEventsTab = setWorldEventsTab;
    }
}());