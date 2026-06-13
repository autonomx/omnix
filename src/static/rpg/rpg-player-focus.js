(function () {
  'use strict';

  var STORAGE_KEY = 'omnix:rpg:player_focus_mode';
  var DEV_STORAGE_KEY = 'omnix:rpg:developer_panels_open';
  var STATUS_ID = 'rpgTurnStatusChip';
  var TOGGLE_ID = 'rpgPlayerFocusToggle';
  var DEV_TOGGLE_ID = 'rpgDeveloperPanelsToggle';
  var WATCHDOG_MS = 18000;
  var lastActiveAt = 0;
  var watchdogTimer = null;

  function $(id) {
    return document.getElementById(id);
  }

  function safeSet(key, value) {
    try { localStorage.setItem(key, value); } catch (_) {}
  }

  function safeGet(key, fallback) {
    try {
      var value = localStorage.getItem(key);
      return value == null ? fallback : value;
    } catch (_) {
      return fallback;
    }
  }

  function isRpgVisible() {
    var view = $('rpgView');
    return !!view && view.style.display !== 'none';
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
    )) {
      return true;
    }
    return !!(node.querySelector && node.querySelector('.rpg-msg, .rpg-turn-narration, .rpg-narration-final'));
  }

  function observeNarrativeFeed() {
    var feed = $('rpgNarrativeFeed');
    if (!feed || feed.dataset.playerFocusObserver === '1') return;
    feed.dataset.playerFocusObserver = '1';
    var observer = new MutationObserver(function (records) {
      for (var i = 0; i < records.length; i += 1) {
        var added = records[i].addedNodes || [];
        for (var j = 0; j < added.length; j += 1) {
          if (hasMeaningfulRpgContent(added[j])) {
            markTurnDone();
            return;
          }
        }
      }
    });
    observer.observe(feed, { childList: true, subtree: true });
  }

  function patchFetchForTurnVisibility() {
    if (window.__rpgPlayerFocusFetchPatched) return;
    window.__rpgPlayerFocusFetchPatched = true;
    var originalFetch = window.fetch;
    if (typeof originalFetch !== 'function') return;
    window.fetch = function (input, init) {
      var url = '';
      try { url = String((input && input.url) || input || ''); } catch (_) { url = ''; }
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

  function init() {
    ensureToolbarControls();
    setFocusMode(safeGet(STORAGE_KEY, '1') !== '0');
    setDeveloperPanels(safeGet(DEV_STORAGE_KEY, '0') === '1');
    observeNarrativeFeed();
    patchFetchForTurnVisibility();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.RpgPlayerFocus = {
    init: init,
    setFocusMode: setFocusMode,
    setDeveloperPanels: setDeveloperPanels,
    markTurnActive: markTurnActive,
    markTurnDone: markTurnDone
  };
}());
