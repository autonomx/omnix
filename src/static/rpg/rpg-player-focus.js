(function () {
  'use strict';

  var STORAGE_KEY = 'omnix:rpg:player_focus_mode';
  var DEV_STORAGE_KEY = 'omnix:rpg:developer_panels_open';
  var RPG_SESSION_KEY = 'omnix_rpg_session_id';
  var RPG_STATE_KEY = 'omnix_rpg_state';
  var RPG_START_ACTION_KEY = 'omnix:rpg:start_action';
  var STATUS_ID = 'rpgTurnStatusChip';
  var TOGGLE_ID = 'rpgPlayerFocusToggle';
  var DEV_TOGGLE_ID = 'rpgDeveloperPanelsToggle';
  var START_MENU_ID = 'rpgStartMenuOverlay';
  var WATCHDOG_MS = 18000;
  var lastActiveAt = 0;
  var watchdogTimer = null;

  function $(id) { return document.getElementById(id); }

  function safeSet(key, value) { try { localStorage.setItem(key, value); } catch (_) {} }
  function safeGet(key, fallback) {
    try {
      var value = localStorage.getItem(key);
      return value == null ? fallback : value;
    } catch (_) { return fallback; }
  }
  function safeRemove(key) { try { localStorage.removeItem(key); } catch (_) {} }
  function safeJsonParse(value) { try { return JSON.parse(value); } catch (_) { return null; } }

  function ensureCombatControlHelper() {
    if (typeof window.rpgUpdateCombatControls === 'function') return;
    window.rpgUpdateCombatControls = function rpgUpdateCombatControls(panel, combatState) {
      if (!panel) return;
      combatState = (combatState && typeof combatState === 'object') ? combatState : {};
      var active = combatState.active === true;
      var currentActorId = String(combatState.current_actor_id || '').toLowerCase();
      var isPlayerTurn = active && (
        currentActorId === 'player' ||
        currentActorId === 'hero' ||
        currentActorId === 'pc' ||
        currentActorId.indexOf('player') === 0
      );

      panel.querySelectorAll('[data-combat-action]').forEach(function (button) {
        var action = button.getAttribute('data-combat-action') || '';
        var isManualResolve = action === 'resolve_current';
        var disabled = !active || (!isPlayerTurn && !isManualResolve);
        button.disabled = disabled;
        button.classList.toggle('is-disabled', disabled);
        button.setAttribute('aria-disabled', disabled ? 'true' : 'false');
        if (!active) button.title = 'Combat is not active.';
        else if (!isPlayerTurn && !isManualResolve) button.title = 'Waiting for the current combat actor.';
        else button.title = '';
      });
    };
  }

  function isRpgVisible() {
    var view = $('rpgView');
    return !!view && view.style.display !== 'none';
  }

  function isPreviewSessionId(value) {
    return String(value || '').trim().indexOf('preview_') === 0;
  }

  function currentSavedSessionId() {
    var sid = safeGet(RPG_SESSION_KEY, '');
    if (sid) return sid;
    var state = safeJsonParse(safeGet(RPG_STATE_KEY, '') || '{}') || {};
    return String(state.sessionId || state.session_id || '');
  }

  function hasSavedRpgSession() {
    var sessionId = currentSavedSessionId();
    if (sessionId && sessionId !== 'session:unknown') return true;
    return !!safeGet(RPG_STATE_KEY, '');
  }

  function clearSavedRpgSession() {
    safeRemove(RPG_SESSION_KEY);
    safeRemove(RPG_STATE_KEY);
    safeRemove('omnix_rpg_last_activity');
    safeRemove('omnix_rpg_last_creator_launch');
  }

  function ensureStatusChip(toolbar) {
    var chip = $(STATUS_ID);
    if (chip || !toolbar) return chip;
    chip = document.createElement('span');
    chip.id = STATUS_ID;
    chip.className = 'rpg-turn-status-chip';
    chip.textContent = 'Waiting for response…';
    toolbar.appendChild(chip);
    return chip;
  }

  function addButton(toolbar, id, label, title, onClick) {
    var existing = $(id);
    if (existing || !toolbar) return existing;
    var btn = document.createElement('button');
    btn.id = id;
    btn.type = 'button';
    btn.className = 'rpg-player-focus-toggle';
    btn.title = title || label;
    btn.textContent = label;
    btn.addEventListener('click', onClick);
    toolbar.appendChild(btn);
    return btn;
  }

  function setFocusMode(enabled) {
    document.body.classList.toggle('rpg-player-focus', !!enabled);
    safeSet(STORAGE_KEY, enabled ? '1' : '0');
    var btn = $(TOGGLE_ID);
    if (btn) {
      btn.textContent = enabled ? '🧭 Player View' : '🧰 Full UI';
      btn.title = enabled ? 'Showing the simplified player view. Click for full UI.' : 'Showing all panels. Click for player view.';
    }
  }

  function setDeveloperPanels(open) {
    document.body.classList.toggle('rpg-dev-panels-open', !!open);
    safeSet(DEV_STORAGE_KEY, open ? '1' : '0');
    var btn = $(DEV_TOGGLE_ID);
    if (btn) {
      btn.textContent = open ? 'Hide Panels' : 'Show Panels';
      btn.title = open ? 'Hide debug/developer panels.' : 'Show hidden debug/developer panels.';
    }
  }

  function ensureToolbarControls() {
    var toolbar = $('rpgToolbar');
    if (!toolbar) return;

    addButton(toolbar, TOGGLE_ID, '🧭 Player View', 'Toggle simplified RPG player view', function () {
      setFocusMode(!document.body.classList.contains('rpg-player-focus'));
    });
    addButton(toolbar, DEV_TOGGLE_ID, 'Show Panels', 'Temporarily show hidden RPG panels', function () {
      setDeveloperPanels(!document.body.classList.contains('rpg-dev-panels-open'));
    });
    ensureStatusChip(toolbar);
  }

  function updateStatusChip(active, stalled) {
    var chip = $(STATUS_ID);
    if (!chip) return;
    chip.classList.toggle('is-active', !!active);
    chip.classList.toggle('is-stalled', !!stalled);
    chip.textContent = stalled ? 'Response is taking longer than expected…' : 'Waiting for response…';
  }

  function ensurePendingNote(stalled) {
    var feed = $('rpgNarrativeFeed');
    if (!feed) return;
    var id = 'rpgPendingResponseNote';
    var note = $(id);
    if (!note) {
      note = document.createElement('div');
      note.id = id;
      note.className = 'rpg-pending-response-note';
      feed.appendChild(note);
    }
    note.classList.toggle('is-stalled', !!stalled);
    note.textContent = stalled
      ? 'Still waiting for the final narration. The command was sent; this usually means the background narration worker is delayed or the endpoint returned an incomplete payload.'
      : 'Command sent. Waiting for the response…';
    feed.scrollTop = feed.scrollHeight;
  }

  function clearPendingNote() {
    var note = $('rpgPendingResponseNote');
    if (note && note.parentNode) note.parentNode.removeChild(note);
  }

  function markTurnActive() {
    if (!isRpgVisible()) return;
    lastActiveAt = Date.now();
    updateStatusChip(true, false);
    ensurePendingNote(false);
    window.clearTimeout(watchdogTimer);
    watchdogTimer = window.setTimeout(function () {
      if (lastActiveAt && Date.now() - lastActiveAt >= WATCHDOG_MS) {
        updateStatusChip(true, true);
        ensurePendingNote(true);
      }
    }, WATCHDOG_MS + 250);
  }

  function markTurnDone() {
    lastActiveAt = 0;
    window.clearTimeout(watchdogTimer);
    updateStatusChip(false, false);
    clearPendingNote();
  }

  function hasMeaningfulRpgContent(node) {
    if (!node || node.nodeType !== 1) return false;
    if (node.id === 'rpgPendingResponseNote') return false;
    if (node.classList && (
      node.classList.contains('rpg-msg') ||
      node.classList.contains('rpg-turn-narration') ||
      node.classList.contains('rpg-narration-final')
    )) return true;
    return !!(node.querySelector && node.querySelector('.rpg-msg, .rpg-turn-narration, .rpg-narration-final'));
  }

  function isGenericAmbientFiller(text) {
    text = String(text || '').toLowerCase();
    return text.indexOf('murmurs a quick thought under their breath') !== -1;
  }

  function cleanAmbientNode(node) {
    if (!node || node.nodeType !== 1) return;
    var cards = [];
    if (node.classList && node.classList.contains('rpg-ambient')) cards.push(node);
    if (node.querySelectorAll) node.querySelectorAll('.rpg-ambient').forEach(function (card) { cards.push(card); });
    cards.forEach(function (card) {
      if (isGenericAmbientFiller(card.textContent || '')) card.remove();
    });
  }

  function observeNarrativeFeed() {
    var feed = $('rpgNarrativeFeed');
    if (!feed || feed.dataset.playerFocusObserver === '1') return;
    feed.dataset.playerFocusObserver = '1';
    var observer = new MutationObserver(function (records) {
      for (var i = 0; i < records.length; i += 1) {
        var added = records[i].addedNodes || [];
        for (var j = 0; j < added.length; j += 1) {
          cleanAmbientNode(added[j]);
          if (hasMeaningfulRpgContent(added[j])) {
            markTurnDone();
            return;
          }
        }
      }
    });
    observer.observe(feed, { childList: true, subtree: true });
    cleanAmbientNode(feed);
  }

  function previewResumeResponse(sessionId) {
    return new Response(JSON.stringify({
      ok: false,
      error: 'preview_session_resume_skipped',
      session_id: sessionId || '',
      updates: [],
      latest_seq: 0,
      ticks_applied: 0,
      excess_summarized: 0,
      world_advance_recap: {}
    }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  }

  function bodyLooksLikePreviewSession(body) {
    var parsed = null;
    if (typeof body === 'string') parsed = safeJsonParse(body);
    else if (body && typeof URLSearchParams !== 'undefined' && body instanceof URLSearchParams) parsed = Object.fromEntries(body.entries());
    var sid = String((parsed && (parsed.session_id || parsed.sessionId)) || '');
    return isPreviewSessionId(sid) ? sid : '';
  }

  function patchFetchForTurnVisibility() {
    if (window.__rpgPlayerFocusFetchPatched) return;
    window.__rpgPlayerFocusFetchPatched = true;
    var originalFetch = window.fetch;
    if (typeof originalFetch !== 'function') return;

    window.fetch = function (input, init) {
      var url = '';
      var body = init && init.body;
      try {
        url = String((input && input.url) || input || '');
        if (!body && input && input.body) body = input.body;
      } catch (_) { url = ''; }

      var isResumeRequest = /\/api\/rpg\/session\/resume(?:$|[?#])/.test(url);
      if (isResumeRequest) {
        var previewSid = bodyLooksLikePreviewSession(body);
        if (!previewSid && isPreviewSessionId(currentSavedSessionId())) previewSid = currentSavedSessionId();
        if (previewSid) {
          console.warn('[RPG] skipped backend resume for preview session', previewSid);
          return Promise.resolve(previewResumeResponse(previewSid));
        }
      }

      var isTurnRequest = /\/api\/rpg\/(games\/[^/]+\/turn|session\/turn|turn_stream|stream_turn)/.test(url);
      if (isTurnRequest) markTurnActive();
      return originalFetch.apply(this, arguments).then(function (response) {
        if (isTurnRequest && !response.ok) {
          updateStatusChip(true, true);
          ensurePendingNote(true);
        }
        return response;
      }).catch(function (err) {
        if (isTurnRequest) {
          updateStatusChip(true, true);
          ensurePendingNote(true);
        }
        throw err;
      });
    };
  }

  function clickWhenAvailable(id, attempts) {
    attempts = attempts == null ? 20 : attempts;
    var btn = $(id);
    if (btn) { btn.click(); return true; }
    if (attempts > 0) window.setTimeout(function () { clickWhenAvailable(id, attempts - 1); }, 150);
    return false;
  }

  function removeStartMenu() {
    var overlay = $(START_MENU_ID);
    if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
  }

  function chooseFreshStart(action) {
    clearSavedRpgSession();
    safeSet(RPG_START_ACTION_KEY, action || 'setup');
    window.location.reload();
  }

  function runDeferredStartAction() {
    var action = safeGet(RPG_START_ACTION_KEY, '');
    if (!action) return false;
    safeRemove(RPG_START_ACTION_KEY);
    clearSavedRpgSession();
    if (action === 'quick') { clickWhenAvailable('rpgQuickAdventureBtn'); return true; }
    clickWhenAvailable('rpgSetupBtn');
    return true;
  }

  function showStartMenu(force) {
    if ($(START_MENU_ID)) return;
    var rpgView = $('rpgView');
    if (!rpgView) return;
    var hasSave = hasSavedRpgSession();
    if (!force && !hasSave) return;

    var overlay = document.createElement('div');
    overlay.id = START_MENU_ID;
    overlay.className = 'rpg-start-menu-backdrop';
    overlay.innerHTML = '' +
      '<section class="rpg-start-menu" role="dialog" aria-modal="true" aria-labelledby="rpgStartMenuTitle">' +
        '<h2 id="rpgStartMenuTitle">RPG Adventure</h2>' +
        '<p>Choose how to begin. Continuing keeps the previous saved session; starting a new adventure clears the saved RPG session first so it cannot silently resume.</p>' +
        '<div class="rpg-start-menu-actions">' +
          (hasSave ? '<button type="button" class="rpg-start-menu-btn" data-rpg-start-action="continue"><strong>Continue Previous Adventure</strong><span>Resume the saved RPG session.</span></button>' : '') +
          '<button type="button" class="rpg-start-menu-btn rpg-start-menu-btn--danger" data-rpg-start-action="quick"><strong>New Quick Adventure</strong><span>Clear the old session and immediately start a default adventure.</span></button>' +
          '<button type="button" class="rpg-start-menu-btn" data-rpg-start-action="setup"><strong>New Custom Adventure</strong><span>Clear the old session and open Adventure Setup.</span></button>' +
        '</div>' +
        (hasSave ? '<div class="rpg-start-menu-save-note">A saved RPG session was found. It will only resume if you choose Continue.</div>' : '') +
      '</section>';

    overlay.addEventListener('click', function (event) {
      var button = event.target && event.target.closest ? event.target.closest('[data-rpg-start-action]') : null;
      if (!button) return;
      var action = button.getAttribute('data-rpg-start-action');
      if (action === 'continue') { removeStartMenu(); return; }
      chooseFreshStart(action);
    });

    document.body.appendChild(overlay);
    var first = overlay.querySelector('[data-rpg-start-action]');
    if (first && first.focus) first.focus();
  }

  function installStartMenuHooks() {
    var toolbar = $('rpgToolbar');
    if (toolbar && !$('rpgStartMenuBtn')) {
      addButton(toolbar, 'rpgStartMenuBtn', '🎲 Game Menu', 'Open RPG start menu', function () { showStartMenu(true); });
    }
    if (runDeferredStartAction()) return;
    if (hasSavedRpgSession()) window.setTimeout(function () { showStartMenu(false); }, 250);
  }

  function init() {
    ensureCombatControlHelper();
    ensureToolbarControls();
    setFocusMode(safeGet(STORAGE_KEY, '1') !== '0');
    setDeveloperPanels(safeGet(DEV_STORAGE_KEY, '0') === '1');
    observeNarrativeFeed();
    patchFetchForTurnVisibility();
    installStartMenuHooks();
  }

  ensureCombatControlHelper();
  patchFetchForTurnVisibility();

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  window.RpgPlayerFocus = {
    init: init,
    setFocusMode: setFocusMode,
    setDeveloperPanels: setDeveloperPanels,
    showStartMenu: showStartMenu,
    clearSavedRpgSession: clearSavedRpgSession,
    markTurnActive: markTurnActive,
    markTurnDone: markTurnDone,
    ensureCombatControlHelper: ensureCombatControlHelper
  };
}());
