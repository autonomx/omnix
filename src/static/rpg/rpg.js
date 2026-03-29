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
        isLoading: false,
    };

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

    // ─── Loading state ─────────────────────────────────────────────────────────

    function setLoading(loading) {
        updateState({ isLoading: loading });
        if (window._currentMode !== 'rpg') return;
        var sendBtn = el('sendBtn');
        var messageInput = el('messageInput');
        if (!sendBtn || !messageInput) return;
        sendBtn.disabled = loading || !messageInput.value.trim();
        messageInput.disabled = loading;
    }

    // ─── API ───────────────────────────────────────────────────────────────────

    async function apiCreateGame() {
        var res = await fetch('/api/rpg/games', { method: 'POST' });
        if (!res.ok) throw new Error('Failed to create game (' + res.status + ')');
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
        };
    }

    // ─── Input handler ─────────────────────────────────────────────────────────

    async function handleRPGInput(input) {
        if (!input || rpgState.isLoading) return;

        appendMessage({ type: 'player', content: input });
        setLoading(true);

        try {
            var data;

            if (!rpgState.sessionId) {
                // First input \u2013 create game (retry once on failure)
                var retried = false;
                while (true) {
                    try {
                        var game = await apiCreateGame();
                        updateState({ sessionId: game.session_id });
                        localStorage.setItem(STORAGE_KEY, rpgState.sessionId);

                        // Show world opening before the player's first turn
                        if (game.opening) {
                            applyUpdate(transformResponse({ narration: game.opening }));
                        }

                        data = await apiSendTurn(rpgState.sessionId, input);
                        break;
                    } catch (err) {
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
                // Subsequent turns \u2013 retry with a fresh session if the stored one expired
                try {
                    data = await apiSendTurn(rpgState.sessionId, input);
                } catch (err) {
                    updateState({ sessionId: null });
                    localStorage.removeItem(STORAGE_KEY);

                    var game2 = await apiCreateGame();
                    updateState({ sessionId: game2.session_id });
                    localStorage.setItem(STORAGE_KEY, rpgState.sessionId);

                    if (game2.opening) {
                        applyUpdate(transformResponse({ narration: game2.opening }));
                    }

                    data = await apiSendTurn(rpgState.sessionId, input);
                }
            }

            applyUpdate(transformResponse(data));
        } catch (err) {
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
                    '<p>Type anything to begin your adventure\u2026</p>' +
                    '<button class="rpg-new-session-btn" id="rpgNewSessionBtn" title="Start a fresh adventure">New Adventure</button>' +
                '</div>';
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
    }

    // ─── Init ──────────────────────────────────────────────────────────────────

    function init() {
        console.log('[RPG] Initializing RPG mode\u2026');

        window._currentMode = 'chat';

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

        // "New Adventure" button — use event delegation on the feed so the
        // listener survives the innerHTML replacement in resetSession().
        var feed = el('rpgNarrativeFeed');
        if (feed) {
            feed.addEventListener('click', function (e) {
                if (e.target && e.target.id === 'rpgNewSessionBtn') resetSession();
            });
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
