(function () {
  'use strict';

  var SESSION_KEY = 'omnix_rpg_session_id';
  var STATE_KEY = 'omnix_rpg_state';
  var WAIT_MS = 1800;
  var activeAt = 0;
  var lastFetchAt = 0;
  var lastCommand = '';
  var recoveryRunning = false;
  var timer = null;

  function log(label, data) {
    try { console.log('[RPG][SubmitWatchdog] ' + label, data || {}); } catch (_) {}
  }

  function $(id) { return document.getElementById(id); }

  function readStorage(key) {
    try { return localStorage.getItem(key) || ''; } catch (_) { return ''; }
  }

  function parseJson(value) {
    try { return JSON.parse(value); } catch (_) { return null; }
  }

  function sessionId() {
    var direct = readStorage(SESSION_KEY);
    if (direct) return direct;
    var state = parseJson(readStorage(STATE_KEY) || '{}') || {};
    return String(state.sessionId || state.session_id || '');
  }

  function normalizeCommand(text) {
    return String(text || '').replace(/^\s*[›>]+\s*/, '').trim();
  }

  function isPlayerNode(node) {
    return !!(node && node.nodeType === 1 && node.classList && node.classList.contains('rpg-msg--player'));
  }

  function isAmbientNode(node) {
    return !!(node && node.nodeType === 1 && node.classList && node.classList.contains('rpg-ambient'));
  }

  function setPending(stalled) {
    var chip = $('rpgTurnStatusChip');
    if (chip) {
      chip.classList.add('is-active');
      chip.classList.toggle('is-stalled', !!stalled);
      chip.textContent = stalled ? 'Response is taking longer than expected…' : 'Waiting for response…';
    }
    var feed = $('rpgNarrativeFeed');
    if (!feed) return;
    var note = $('rpgPendingResponseNote');
    if (!note) {
      note = document.createElement('div');
      note.id = 'rpgPendingResponseNote';
      note.className = 'rpg-pending-response-note';
      feed.appendChild(note);
    }
    note.classList.toggle('is-stalled', !!stalled);
    note.textContent = stalled
      ? 'Still waiting for the GM/NPC response. The submit path did not start a turn stream, so Omnix is recovering the turn now.'
      : 'Command sent. Waiting for the GM/NPC response…';
  }

  function clearPending() {
    activeAt = 0;
    window.clearTimeout(timer);
    var chip = $('rpgTurnStatusChip');
    if (chip) {
      chip.classList.remove('is-active', 'is-stalled');
      chip.textContent = 'Waiting for response…';
    }
    var note = $('rpgPendingResponseNote');
    if (note && note.parentNode) note.parentNode.removeChild(note);
  }

  function appendResponse(text) {
    text = String(text || '').trim();
    if (!text) return;
    var feed = $('rpgNarrativeFeed');
    if (!feed) return;
    var msg = document.createElement('div');
    msg.className = 'rpg-msg rpg-msg--narration rpg-msg--watchdog-response';
    msg.textContent = text;
    feed.appendChild(msg);
    feed.scrollTop = feed.scrollHeight;
    log('rendered_recovered_response', { text: text.slice(0, 160) });
    clearPending();
  }

  function usefulText(event) {
    if (!event || typeof event !== 'object') return '';
    var artifact = event.narration_artifact && typeof event.narration_artifact === 'object' ? event.narration_artifact : {};
    return String(
      event.narration ||
      event.fallback_narration ||
      event.deterministic_fallback_narration ||
      event.summary ||
      artifact.narration ||
      artifact.authoritative_action ||
      ''
    ).trim();
  }

  function recoverTurn() {
    var sid = sessionId();
    var command = String(lastCommand || '').trim();
    if (recoveryRunning || !sid || !command) return;
    recoveryRunning = true;
    setPending(true);
    log('recovery_stream_start', { session_id: sid, command: command });

    fetch('/api/rpg/session/turn/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sid, input: command, player_input: command, watchdog_recovery: true })
    }).then(function (response) {
      log('recovery_stream_response', { status: response.status, ok: response.ok });
      if (!response.ok || !response.body || !response.body.getReader) throw new Error('turn_stream_unavailable_' + response.status);
      var reader = response.body.getReader();
      var decoder = new TextDecoder();
      var buffer = '';
      function pump() {
        return reader.read().then(function (next) {
          if (!next || next.done) return;
          buffer += decoder.decode(next.value, { stream: true });
          var parts = buffer.split('\n\n');
          buffer = parts.pop() || '';
          for (var i = 0; i < parts.length; i += 1) {
            var lines = String(parts[i] || '').split('\n')
              .filter(function (line) { return String(line || '').indexOf('data:') === 0; })
              .map(function (line) { return line.slice(5).trim(); });
            if (!lines.length) continue;
            var event = parseJson(lines.join('\n'));
            var text = usefulText(event);
            log('recovery_stream_event', { type: event && event.type, has_text: !!text });
            if (text) {
              try { reader.cancel('watchdog response rendered'); } catch (_) {}
              appendResponse(text);
              return;
            }
          }
          return pump();
        });
      }
      return pump();
    }).catch(function (error) {
      log('recovery_stream_error', { message: String(error && error.message || error) });
      setPending(true);
    }).finally(function () {
      recoveryRunning = false;
    });
  }

  function arm(command) {
    lastCommand = normalizeCommand(command);
    activeAt = Date.now();
    setPending(false);
    window.clearTimeout(timer);
    timer = window.setTimeout(function () {
      if (!activeAt) return;
      if (lastFetchAt && lastFetchAt >= activeAt) return;
      log('no_turn_stream_fetch_detected', {
        age_ms: Date.now() - activeAt,
        session_id: sessionId(),
        command: lastCommand
      });
      recoverTurn();
    }, WAIT_MS);
  }

  function observeFeed() {
    var feed = $('rpgNarrativeFeed');
    if (!feed || feed.dataset.submitWatchdog === '1') return;
    feed.dataset.submitWatchdog = '1';
    new MutationObserver(function (records) {
      records.forEach(function (record) {
        Array.prototype.forEach.call(record.addedNodes || [], function (node) {
          if (isPlayerNode(node)) {
            arm(node.textContent || '');
            log('player_command_seen', { command: lastCommand, session_id: sessionId() });
            return;
          }
          if (isAmbientNode(node)) {
            log('ambient_ignored', { text: String(node.textContent || '').slice(0, 160) });
            return;
          }
          if (node && node.nodeType === 1 && node.classList && node.classList.contains('rpg-msg') && !isPlayerNode(node)) {
            log('response_node_seen', { class_name: node.className || '', text: String(node.textContent || '').slice(0, 160) });
            clearPending();
          }
        });
      });
    }).observe(feed, { childList: true, subtree: true });
  }

  function patchFetch() {
    if (window.__rpgSubmitWatchdogFetchPatched) return;
    window.__rpgSubmitWatchdogFetchPatched = true;
    var originalFetch = window.fetch;
    if (typeof originalFetch !== 'function') return;
    window.fetch = function (input, init) {
      var url = '';
      try { url = String((input && input.url) || input || ''); } catch (_) { url = ''; }
      if (/\/api\/rpg\/session\/turn\/stream(?:$|[?#])/.test(url)) {
        lastFetchAt = Date.now();
        log('turn_stream_fetch_seen', { url: url, age_ms: activeAt ? lastFetchAt - activeAt : 0 });
      }
      return originalFetch.apply(this, arguments);
    };
  }

  function init() {
    observeFeed();
    patchFetch();
    log('init', { session_id: sessionId() });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
}());
