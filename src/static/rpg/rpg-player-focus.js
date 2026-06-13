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
  var WATCHDOG_MS = 6000;
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
      ? 'Still waiting for the GM/NPC response. The command was accepted, but the live narration stream has not returned response content yet.'
      : 'Command sent. Waiting for the GM/NPC response…';
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

  function isPlayerMessageNode(node) {
    if (!node || node.nodeType !== 1 || !node.classList) return false;
    return node.classList.contains('rpg-msg--player');
  }

  function isResponseMessageNode(node) {
    if (!node || node.nodeType !== 1 || !node.classList) return false;
    if (!node.classList.contains('rpg-msg')) return false;
    if (isPlayerMessageNode(node)) return false;
    var text = String(node.textContent || '').trim();
    if (!text) return false;
    return true;
  }

  function hasMeaningfulRpgContent(node) {
    if (!node || node.nodeType !== 1) return false;
    if (node.id === 'rpgPendingResponseNote') return false;
    if (isResponseMessageNode(node)) return true;
    if (node.classList && (
      node.classList.contains('rpg-turn-narration') ||
      node.classList.contains('rpg-narration-final')
    )) return String(node.textContent || '').trim().length > 0;
    if (!node.querySelectorAll) return false;
    var candidates = node.querySelectorAll('.rpg-msg, .rpg-turn-narration, .rpg-narration-final');
    for (var i = 0; i < candidates.length; i += 1) {
      if (isResponseMessageNode(candidates[i])) return true;
      if (!isPlayerMessageNode(candidates[i]) && String(candidates[i].textContent || '').trim()) return true;
    }
    return false;
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

  function requestBodyObject(body) {
    if (typeof body === 'string') return safeJsonParse(body) || {};
    if (body && typeof URLSearchParams !== 'undefined' && body instanceof URLSearchParams) return Object.fromEntries(body.entries());
    return {};
  }

  function bodyLooksLikePreviewSession(body) {
    var parsed = requestBodyObject(body);
    var sid = String((parsed && (parsed.session_id || parsed.sessionId)) || '');
    return isPreviewSessionId(sid) ? sid : '';
  }

  function sse(data) {
    return 'data: ' + JSON.stringify(data || {}) + '\n\n';
  }

  function encodeText(text) {
    return new TextEncoder().encode(text || '');
  }

  function wrapTurnStreamResponseWithAuthoritativeFallback(response) {
    if (!response || !response.body || typeof ReadableStream === 'undefined') return response;
    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';
    var fallbackEmitted = false;

    var stream = new ReadableStream({
      start: function (controller) {
        function pump() {
          reader.read().then(function (next) {
            if (!next || next.done) {
              if (!fallbackEmitted && buffer) controller.enqueue(encodeText(buffer));
              controller.close();
              return;
            }

            var chunkText = decoder.decode(next.value, { stream: true });
            buffer += chunkText;
            var parts = buffer.split('\n\n');
            buffer = parts.pop() || '';

            for (var i = 0; i < parts.length; i += 1) {
              var raw = parts[i];
              controller.enqueue(encodeText(raw + '\n\n'));
              if (fallbackEmitted) continue;

              var dataLines = String(raw || '').split('\n')
                .filter(function (line) { return String(line || '').indexOf('data:') === 0; })
                .map(function (line) { return line.slice(5).trim(); });
              if (!dataLines.length) continue;

              var evt = safeJsonParse(dataLines.join('\n'));
              if (!evt || evt.type !== 'authoritative_result') continue;

              var fallback = String(evt.fallback_narration || evt.summary || '').trim();
              if (!fallback) continue;

              fallbackEmitted = true;
              var turnId = String(evt.turn_id || 'authoritative_fallback_' + Date.now());
              controller.enqueue(encodeText(sse({
                type: 'narration_artifact',
                turn_id: turnId,
                narration: fallback,
                authoritative_action: fallback,
                live_draft_streaming: true,
                source: 'authoritative_fallback_before_live_narration'
              })));
              controller.enqueue(encodeText(sse({
                type: 'done',
                turn_id: turnId,
                tick: evt.tick,
                narration_status: 'authoritative_fallback',
                live_draft_streaming: true
              })));
              try { reader.cancel('authoritative fallback delivered'); } catch (_) {}
              controller.close();
              return;
            }

            pump();
          }).catch(function (err) {
            controller.error(err);
          });
        }
        pump();
      },
      cancel: function (reason) {
        try { reader.cancel(reason); } catch (_) {}
      }
    });

    return new Response(stream, {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers
    });
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

      var isTurnStreamRequest = /\/api\/rpg\/session\/turn\/stream(?:$|[?#])/.test(url);
      var isTurnRequest = /\/api\/rpg\/(games\/[^/]+\/turn|session\/turn(?:\/stream)?|turn_stream|stream_turn)(?:$|[?#])/.test(url);
      if (isTurnRequest) markTurnActive();

      return originalFetch.apply(this, arguments).then(function (response) {
        if (isTurnRequest && !response.ok) {
          updateStatusChip(true, true);
          ensurePendingNote(true);
        }
        if (isTurnStreamRequest && response.ok) {
          return wrapTurnStreamResponseWithAuthoritativeFallback(response);
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
    if (!force && !hasSavedRpgSession()) return;

    var hasSave = hasSavedRpgSession();
    var overlay = document.createElement('div');
    overlay.id = START_MENU_ID;
    overlay.className = 'rpg-start-menu-overlay';
    overlay.innerHTML = '' +
      '<div class="rpg-start-menu-card" role="dialog" aria-modal="true" aria-label="RPG game menu">' +
      '<div class="rpg-start-menu-kicker">Omnix RPG</div>' +
      '<h2>Choose your adventure</h2>' +
      '<p>Start fresh or continue your last runtime session.</p>' +
      '<div class="rpg-start-menu-actions">' +
      (hasSave ? '<button type="button" id="rpgStartContinue" class="rpg-start-primary">Continue Previous Adventure</button>' : '') +
      '<button type="button" id="rpgStartQuick" class="rpg-start-secondary">New Quick Adventure</button>' +
      '<button type="button" id="rpgStartSetup" class="rpg-start-secondary">New Custom Adventure</button>' +
      '</div>' +
      '</div>';
    rpgView.appendChild(overlay);

    var continueBtn = $('rpgStartContinue');
    var quickBtn = $('rpgStartQuick');
    var setupBtn = $('rpgStartSetup');
    if (continueBtn) continueBtn.addEventListener('click', removeStartMenu);
    if (quickBtn) quickBtn.addEventListener('click', function () { chooseFreshStart('quick'); });
    if (setupBtn) setupBtn.addEventListener('click', function () { chooseFreshStart('setup'); });
  }

  function ensureGameMenuButton() {
    var toolbar = $('rpgToolbar');
    if (!toolbar || $('rpgGameMenuButton')) return;
    addButton(toolbar, 'rpgGameMenuButton', '🎲 Game Menu', 'Open RPG game menu', function () {
      showStartMenu(true);
    });
  }

  function init() {
    ensureCombatControlHelper();
    ensureToolbarControls();
    ensureGameMenuButton();
    setFocusMode(safeGet(STORAGE_KEY, '1') !== '0');
    setDeveloperPanels(safeGet(DEV_STORAGE_KEY, '0') === '1');
    observeNarrativeFeed();
    patchFetchForTurnVisibility();
    if (!runDeferredStartAction()) showStartMenu(false);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();

  window.RpgPlayerFocus = {
    init: init,
    setFocusMode: setFocusMode,
    setDeveloperPanels: setDeveloperPanels,
    markTurnActive: markTurnActive,
    markTurnDone: markTurnDone,
    showStartMenu: showStartMenu,
    clearSavedRpgSession: clearSavedRpgSession
  };
}());
