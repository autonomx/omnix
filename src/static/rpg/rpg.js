/**
 * Omnix RPG Mode
 *
 * Implements a mode toggle (Chat / RPG) and the full RPG storytelling UI:
 *   - NarrativeFeed   – scrollable story log with fade-in animation
 *   - ChoicePanel     – action buttons rendered from API choices[]
 *   - NPCPanel        – per-NPC cards with relationship bar + action buttons
 *   - DiceRollOverlay – animated roll results, auto-hides after 4 s
 *   - MinimapPanel    – zone grid with active/danger highlights
 *
 * API contract (existing backend):
 *   POST /api/rpg/games              → { session_id, opening, world, player }
 *   POST /api/rpg/games/:id/turn     → { narration, choices?, dice_roll?,
 *                                        events?, fail_state?,
 *                                        npcs?, rolls?, map? }
 *
 * The module does NOT touch any chat logic; it only intercepts the shared
 * send-button / textarea when RPG mode is active.
 */

(function () {
    'use strict';

    // ─── Constants ─────────────────────────────────────────────────────────────

    const STORAGE_KEY = 'omnix_rpg_session_id';
    const DICE_HIDE_DELAY = 4000; // ms

    // ─── State ─────────────────────────────────────────────────────────────────

    const rpgState = {
        sessionId: null,
        messages: [],   // { type: 'narration'|'event'|'system'|'player', content }
        choices: [],
        npcs: [],
        rolls: [],
        map: null,
        isLoading: false,
    };

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
        rpgState.isLoading = loading;
        if (window._currentMode !== 'rpg') return;
        const sendBtn = el('sendBtn');
        const messageInput = el('messageInput');
        if (!sendBtn || !messageInput) return;
        sendBtn.disabled = loading || !messageInput.value.trim();
        messageInput.disabled = loading;
    }

    // ─── API ───────────────────────────────────────────────────────────────────

    async function apiCreateGame() {
        const res = await fetch('/api/rpg/games', { method: 'POST' });
        if (!res.ok) throw new Error(`Failed to create game (${res.status})`);
        return res.json();
    }

    async function apiSendTurn(sessionId, input) {
        const res = await fetch(`/api/rpg/games/${encodeURIComponent(sessionId)}/turn`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ input }),
        });
        if (!res.ok) throw new Error(`Turn request failed (${res.status})`);
        return res.json();
    }

    // ─── Response transform ────────────────────────────────────────────────────

    function transformResponse(data) {
        const messages = [];

        if (data.narration) {
            messages.push({ type: 'narration', content: data.narration });
        }

        if (Array.isArray(data.events)) {
            data.events.forEach(ev => {
                const text = ev.description || ev.type || JSON.stringify(ev);
                messages.push({ type: 'event', content: text });
            });
        }

        if (data.fail_state) {
            const text = data.fail_state.description || data.fail_state.type || 'Something went wrong…';
            messages.push({ type: 'system', content: `⚠️ ${text}` });
        }

        // Normalise dice rolls: API may return dice_roll (single obj) or rolls (array)
        const rolls = Array.isArray(data.rolls)
            ? data.rolls
            : (data.dice_roll ? [data.dice_roll] : []);

        return {
            messages,
            choices: data.choices || [],
            npcs:    data.npcs    || [],
            rolls,
            map:     data.map     || null,
        };
    }

    // ─── Input handler ─────────────────────────────────────────────────────────

    async function handleRPGInput(input) {
        if (!input || rpgState.isLoading) return;

        appendMessage({ type: 'player', content: input });
        setLoading(true);

        try {
            let data;

            if (!rpgState.sessionId) {
                // First input – create game (retry once on failure)
                let retried = false;
                while (true) {
                    try {
                        const game = await apiCreateGame();
                        rpgState.sessionId = game.session_id;
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
                            rpgState.sessionId = null;
                            localStorage.removeItem(STORAGE_KEY);
                            continue;
                        }
                        throw err;
                    }
                }
            } else {
                // Subsequent turns – retry with a fresh session if the stored one expired
                try {
                    data = await apiSendTurn(rpgState.sessionId, input);
                } catch (err) {
                    rpgState.sessionId = null;
                    localStorage.removeItem(STORAGE_KEY);

                    const game = await apiCreateGame();
                    rpgState.sessionId = game.session_id;
                    localStorage.setItem(STORAGE_KEY, rpgState.sessionId);

                    if (game.opening) {
                        applyUpdate(transformResponse({ narration: game.opening }));
                    }

                    data = await apiSendTurn(rpgState.sessionId, input);
                }
            }

            applyUpdate(transformResponse(data));
        } catch (err) {
            appendMessage({ type: 'system', content: `❌ Error: ${err.message}` });
        } finally {
            setLoading(false);
        }
    }

    // ─── Apply update ──────────────────────────────────────────────────────────

    function applyUpdate(update) {
        update.messages.forEach(msg => {
            rpgState.messages.push(msg);
            appendMessage(msg);
        });

        rpgState.choices = update.choices;
        renderChoices();

        if (update.npcs && update.npcs.length) {
            rpgState.npcs = update.npcs;
            renderNPCs();
        }

        if (update.rolls && update.rolls.length) {
            rpgState.rolls = update.rolls;
            renderDiceRolls();
        }

        if (update.map) {
            rpgState.map = update.map;
            renderMap();
        }
    }

    // ─── Rendering: Narrative Feed ─────────────────────────────────────────────

    function appendMessage(msg) {
        const feed = el('rpgNarrativeFeed');
        if (!feed) return;

        // Hide the empty-state welcome card once there is content
        const welcome = el('rpgWelcome');
        if (welcome) welcome.style.display = 'none';

        const div = document.createElement('div');
        div.className = `rpg-msg rpg-msg--${msg.type}`;

        switch (msg.type) {
            case 'narration':
                // Use marked.js if available for light markdown rendering
                div.innerHTML = (typeof marked !== 'undefined')
                    ? marked.parse(msg.content)
                    : escapeHtml(msg.content).replace(/\n/g, '<br>');
                break;

            case 'player':
                div.innerHTML =
                    `<span class="rpg-msg-player-icon">›</span> <em>${escapeHtml(msg.content)}</em>`;
                break;

            case 'event':
                div.innerHTML =
                    `<span class="rpg-msg-event-icon">🎲</span> ${escapeHtml(msg.content)}`;
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
        const panel = el('rpgChoicePanel');
        if (!panel) return;

        panel.innerHTML = '';

        if (!rpgState.choices || !rpgState.choices.length) {
            panel.style.display = 'none';
            return;
        }

        panel.style.display = 'flex';
        rpgState.choices.forEach(choice => {
            const btn = document.createElement('button');
            btn.className = 'rpg-choice-btn';
            btn.textContent = choice;
            btn.addEventListener('click', () => {
                if (!rpgState.isLoading) handleRPGInput(choice);
            });
            panel.appendChild(btn);
        });
    }

    // ─── Rendering: NPC Panel ──────────────────────────────────────────────────

    function getMoodClass(mood) {
        if (!mood) return '';
        const m = mood.toLowerCase();
        if (['friendly', 'happy', 'welcoming', 'grateful'].some(w => m.includes(w))) return 'rpg-npc-mood--friendly';
        if (['hostile', 'angry', 'aggressive', 'furious'].some(w => m.includes(w))) return 'rpg-npc-mood--hostile';
        if (['suspicious', 'wary', 'cautious', 'nervous'].some(w => m.includes(w))) return 'rpg-npc-mood--wary';
        return '';
    }

    function renderNPCs() {
        const wrapper = el('rpgNPCPanelWrapper');
        const panel = el('rpgNPCPanel');
        if (!panel || !wrapper) return;

        if (!rpgState.npcs || !rpgState.npcs.length) {
            wrapper.style.display = 'none';
            return;
        }

        wrapper.style.display = 'block';
        panel.innerHTML = '';

        rpgState.npcs.forEach(npc => {
            const card = document.createElement('div');
            card.className = 'rpg-npc-card';

            const moodClass = getMoodClass(npc.mood);

            // Relationship bar: API uses -100..100; normalise to 0..100%
            const relPct = (npc.relationship != null)
                ? Math.max(0, Math.min(100, (npc.relationship + 100) / 2))
                : null;
            const relColor = (npc.relationship != null && npc.relationship >= 0) ? '#22c55e' : '#ef4444';
            const relBar = (relPct != null)
                ? `<div class="rpg-npc-rel-bar">
                     <div class="rpg-npc-rel-fill" style="width:${relPct}%;background:${relColor}"></div>
                   </div>`
                : '';

            card.innerHTML = `
                <div class="rpg-npc-name">${escapeHtml(npc.name || 'Unknown')}</div>
                <div class="rpg-npc-mood ${moodClass}">${escapeHtml(npc.mood || '')}</div>
                ${relBar}
                <div class="rpg-npc-actions">
                    <button class="rpg-npc-btn"
                            data-npc="${escapeHtml(npc.name || '')}"
                            data-action="talk">Talk</button>
                    <button class="rpg-npc-btn rpg-npc-btn--threat"
                            data-npc="${escapeHtml(npc.name || '')}"
                            data-action="threaten">Threaten</button>
                </div>`;

            card.querySelectorAll('.rpg-npc-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    if (rpgState.isLoading) return;
                    handleRPGInput(`${btn.dataset.action} ${btn.dataset.npc}`);
                });
            });

            panel.appendChild(card);
        });
    }

    // ─── Rendering: Dice Roll Overlay ──────────────────────────────────────────

    function renderDiceRolls() {
        const overlay = el('rpgDiceOverlay');
        if (!overlay) return;

        if (!rpgState.rolls || !rpgState.rolls.length) {
            overlay.style.display = 'none';
            return;
        }

        overlay.innerHTML = rpgState.rolls.map(roll => {
            const success = roll.success !== false;
            const total   = roll.total  != null ? roll.total : roll.result;
            const label   = roll.type   || roll.dice || 'd20';
            const modStr  = (roll.modifier != null && roll.modifier !== 0)
                ? ` + ${roll.modifier}`
                : '';

            return `<div class="rpg-dice-roll ${success ? 'rpg-dice-roll--success' : 'rpg-dice-roll--fail'}">
                🎲 ${escapeHtml(label)}: ${roll.result}${modStr} = <strong>${total}</strong>
                <span class="rpg-dice-badge ${success ? 'rpg-dice-badge--success' : 'rpg-dice-badge--fail'}">
                    ${success ? '✓' : '✗'}
                </span>
            </div>`;
        }).join('');

        overlay.style.display = 'flex';

        // Auto-hide
        clearTimeout(overlay._hideTimer);
        overlay._hideTimer = setTimeout(() => {
            overlay.style.display = 'none';
        }, DICE_HIDE_DELAY);
    }

    // ─── Rendering: Minimap ────────────────────────────────────────────────────

    function renderMap() {
        const panel    = el('rpgMinimapPanel');
        const minimap  = el('rpgMinimap');
        if (!panel || !minimap || !rpgState.map) return;

        const map = rpgState.map;
        if (!Array.isArray(map.zones) || !map.zones.length) {
            panel.style.display = 'none';
            return;
        }

        panel.style.display = 'block';
        minimap.innerHTML = map.zones.map(zone => {
            const isActive    = zone.id === map.current_zone;
            const dangerClass = zone.danger >= 4 ? 'rpg-zone--danger'
                              : zone.danger >= 2 ? 'rpg-zone--caution'
                              : '';
            const ownerTitle  = zone.owner ? ` title="Owner: ${escapeHtml(zone.owner)}"` : '';
            return `<div class="rpg-zone ${isActive ? 'rpg-zone--active' : ''} ${dangerClass}"${ownerTitle}>
                ${escapeHtml(zone.id || '?')}
            </div>`;
        }).join('');
    }

    // ─── Mode switching ────────────────────────────────────────────────────────

    function switchMode(mode) {
        window._currentMode = mode;

        const chatContainer = el('chatContainer');
        const rpgView       = el('rpgView');
        const chatModeBtn   = el('chatModeBtn');
        const rpgModeBtn    = el('rpgModeBtn');
        const messageInput  = el('messageInput');
        const sendBtn       = el('sendBtn');

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
            if (messageInput)  messageInput.placeholder = 'Type your message…';
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
        const sendBtn      = el('sendBtn');
        const messageInput = el('messageInput');
        if (!sendBtn || !messageInput) return;

        sendBtn.addEventListener('click', function (e) {
            if (window._currentMode !== 'rpg') return;
            e.stopImmediatePropagation();
            const input = messageInput.value.trim();
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
                const input = messageInput.value.trim();
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
        document.querySelectorAll('.rpg-panel-collapse').forEach(btn => {
            btn.addEventListener('click', () => {
                const target = el(btn.dataset.target);
                if (!target) return;
                const collapsed = target.style.display === 'none';
                target.style.display = collapsed ? '' : 'none';
                btn.textContent = collapsed ? '▼' : '▶';
            });
        });
    }

    // ─── New-session / reset ───────────────────────────────────────────────────

    function resetSession() {
        rpgState.sessionId = null;
        rpgState.messages  = [];
        rpgState.choices   = [];
        rpgState.npcs      = [];
        rpgState.rolls     = [];
        rpgState.map       = null;
        localStorage.removeItem(STORAGE_KEY);

        const feed = el('rpgNarrativeFeed');
        if (feed) {
            feed.innerHTML = `
                <div class="rpg-welcome" id="rpgWelcome">
                    <div class="rpg-welcome-icon">⚔️</div>
                    <h3>RPG Mode</h3>
                    <p>Type anything to begin your adventure…</p>
                </div>`;
        }

        const choicePanel = el('rpgChoicePanel');
        if (choicePanel) { choicePanel.style.display = 'none'; choicePanel.innerHTML = ''; }

        const npcWrapper = el('rpgNPCPanelWrapper');
        if (npcWrapper) npcWrapper.style.display = 'none';

        const diceOverlay = el('rpgDiceOverlay');
        if (diceOverlay) diceOverlay.style.display = 'none';

        const minimapPanel = el('rpgMinimapPanel');
        if (minimapPanel) minimapPanel.style.display = 'none';
    }

    // ─── Init ──────────────────────────────────────────────────────────────────

    function init() {
        console.log('[RPG] Initializing RPG mode…');

        window._currentMode = 'chat';

        // Restore persisted session id (will retry fresh session on first failure)
        const storedId = localStorage.getItem(STORAGE_KEY);
        if (storedId) rpgState.sessionId = storedId;

        // Mode toggle
        const chatModeBtn = el('chatModeBtn');
        const rpgModeBtn  = el('rpgModeBtn');
        if (chatModeBtn) chatModeBtn.addEventListener('click', () => switchMode('chat'));
        if (rpgModeBtn)  rpgModeBtn.addEventListener('click',  () => switchMode('rpg'));

        // New adventure button
        const newSessionBtn = el('rpgNewSessionBtn');
        if (newSessionBtn) newSessionBtn.addEventListener('click', resetSession);

        // Sidebar shortcuts (expanded + collapsed)
        ['rpgBtnOption', 'rpgBtnCollapsed'].forEach(id => {
            const btn = el(id);
            if (btn) btn.addEventListener('click', () => switchMode('rpg'));
        });

        setupCollapsible();
        setupInputIntercept();

        console.log('[RPG] RPG mode ready');
    }

    // Defer until after all other scripts have initialised
    document.addEventListener('DOMContentLoaded', () => setTimeout(init, 650));

    // Public API (handy for debugging from the console)
    window.RPGMode = {
        state:       rpgState,
        reset:       resetSession,
        switchMode,
        handleInput: handleRPGInput,
    };
}());
