(function () {
  'use strict';

  var SESSION_KEY = 'omnix_rpg_session_id';
  var STATE_KEY = 'omnix_rpg_state';
  var WAIT_MS = 1800;
  var FETCH_SEEN_GRACE_MS = 5000;
  var activeAt = 0;
  var lastFetchAt = 0;
  var lastCommand = '';
  var recoveryRunning = false;
  var timer = null;
  var perfSeq = 0;
  var perfById = {};
  var recentPerfSummaries = [];

  function log(label, data) {
    try { console.log('[RPG][SubmitWatchdog] ' + label, data || {}); } catch (_) {}
  }

  function perfNow() {
    try {
      if (window.performance && typeof window.performance.now === 'function') {
        return window.performance.now();
      }
    } catch (_) {}
    return Date.now();
  }

  function roundMs(value) {
    value = Number(value || 0);
    return Math.round(value * 10) / 10;
  }

  function compactUrl(url) {
    url = String(url || '');
    try {
      var parsed = new URL(url, window.location.href);
      return parsed.pathname + parsed.search;
    } catch (_) {
      return url;
    }
  }

  function perfConsole(label, payload) {
    try { console.info('[RPG][Perf] ' + label, payload || {}); } catch (_) {}
  }

  function startPerfSpan(url, init) {
    var startedAt = perfNow();
    var id = 'rpgperf_' + (++perfSeq).toString(36) + '_' + Date.now().toString(36);
    var body = init && init.body;
    var inputPreview = '';
    try {
      var parsed = body && typeof body === 'string' ? JSON.parse(body) : null;
      inputPreview = String((parsed && (parsed.player_input || parsed.input)) || '').slice(0, 100);
    } catch (_) {}
    var span = {
      id: id,
      url: compactUrl(url),
      startedAt: startedAt,
      inputPreview: inputPreview,
      events: [],
      counters: {},
      firstEventAt: 0,
      firstTokenAt: 0,
      authoritativeAt: 0,
      firstVisibleAt: 0,
      doneAt: 0,
      artifactAt: 0,
      errorAt: 0,
      responseHeadersAt: 0
    };
    perfById[id] = span;
    perfConsole('fetch_start', {
      id: id,
      url: span.url,
      method: (init && init.method) || 'GET',
      session_id: sessionId(),
      active_command_age_ms: activeAt ? roundMs(Date.now() - activeAt) : 0,
      input_preview: inputPreview
    });
    return span;
  }

  function markPerf(span, label, extra) {
    if (!span) return;
    var elapsed = roundMs(perfNow() - span.startedAt);
    var payload = Object.assign({
      id: span.id,
      url: span.url,
      label: label,
      elapsed_ms: elapsed
    }, extra || {});
    span.events.push(payload);
    perfConsole(label, payload);
  }

  function summarizePerf(span, reason) {
    if (!span || span._summarized) return;
    span._summarized = true;
    var totalMs = roundMs(perfNow() - span.startedAt);
    var summary = {
      id: span.id,
      url: span.url,
      reason: reason || 'complete',
      total_ms: totalMs,
      headers_ms: span.responseHeadersAt ? roundMs(span.responseHeadersAt - span.startedAt) : null,
      first_sse_ms: span.firstEventAt ? roundMs(span.firstEventAt - span.startedAt) : null,
      authoritative_result_ms: span.authoritativeAt ? roundMs(span.authoritativeAt - span.startedAt) : null,
      first_visible_ms: span.firstVisibleAt ? roundMs(span.firstVisibleAt - span.startedAt) : null,
      first_token_ms: span.firstTokenAt ? roundMs(span.firstTokenAt - span.startedAt) : null,
      artifact_ms: span.artifactAt ? roundMs(span.artifactAt - span.startedAt) : null,
      done_ms: span.doneAt ? roundMs(span.doneAt - span.startedAt) : null,
      error_ms: span.errorAt ? roundMs(span.errorAt - span.startedAt) : null,
      event_counts: span.counters,
      input_preview: span.inputPreview
    };
    recentPerfSummaries.push(summary);
    if (recentPerfSummaries.length > 20) recentPerfSummaries.shift();
    try { window.__rpgTurnPerfSummaries = recentPerfSummaries.slice(); } catch (_) {}
    perfConsole('summary', summary);
    try { console.table([summary]); } catch (_) {}
  }

  function parseSseParts(buffer) {
    var parts = buffer.split('\n\n');
    return { parts: parts.slice(0, -1), rest: parts[parts.length - 1] || '' };
  }

  function eventVisibleTextLength(evt) {
    evt = evt && typeof evt === 'object' ? evt : {};
    var artifact = evt.narration_artifact && typeof evt.narration_artifact === 'object' ? evt.narration_artifact : evt;
    return String(
      evt.narration ||
      evt.fallback_narration ||
      evt.deterministic_fallback_narration ||
      evt.summary ||
      evt.text ||
      artifact.narration ||
      artifact.full_text ||
      artifact.raw_text ||
      ''
    ).length;
  }

  function trackSseEvent(span, evt) {
    if (!span || !evt || typeof evt !== 'object') return;
    var now = perfNow();
    var type = String(evt.type || 'unknown');
    span.counters[type] = (span.counters[type] || 0) + 1;
    if (!span.firstEventAt) span.firstEventAt = now;
    if (type === 'token' && !span.firstTokenAt) span.firstTokenAt = now;
    if (type === 'authoritative_result' && !span.authoritativeAt) span.authoritativeAt = now;
    if ((type === 'narration_artifact' || type === 'narration_complete') && !span.artifactAt) span.artifactAt = now;
    if (type === 'done' && !span.doneAt) span.doneAt = now;
    if (type === 'error' && !span.errorAt) span.errorAt = now;
    if (!span.firstVisibleAt && eventVisibleTextLength(evt) > 0) span.firstVisibleAt = now;

    if (type !== 'heartbeat' || span.counters[type] === 1 || span.counters[type] % 25 === 0) {
      markPerf(span, 'sse_' + type, {
        event_count: span.counters[type],
        stage: evt.stage || '',
        turn_id: evt.turn_id || '',
        tick: evt.tick,
        narration_status: evt.narration_status || evt.status || '',
        live_draft_streaming: !!evt.live_draft_streaming,
        visible_text_len: eventVisibleTextLength(evt)
      });
    }
  }

  function monitorTurnStreamClone(span, response) {
    if (!span || !response || !response.body || !response.clone) return;
    var clone;
    try { clone = response.clone(); } catch (err) {
      markPerf(span, 'clone_unavailable', { message: String(err && err.message || err) });
      return;
    }
    var reader;
    try { reader = clone.body.getReader(); } catch (err2) {
      markPerf(span, 'clone_reader_unavailable', { message: String(err2 && err2.message || err2) });
      return;
    }
    var decoder = new TextDecoder();
    var buffer = '';
    function pump() {
      return reader.read().then(function (next) {
        if (!next || next.done) {
          summarizePerf(span, 'stream_done');
          return;
        }
        buffer += decoder.decode(next.value, { stream: true });
        var parsed = parseSseParts(buffer);
        buffer = parsed.rest;
        parsed.parts.forEach(function (part) {
          var lines = String(part || '').split('\n')
            .filter(function (line) { return String(line || '').indexOf('data:') === 0; })
            .map(function (line) { return line.slice(5).trim(); });
          if (!lines.length) return;
          var evt = parseJson(lines.join('\n'));
          trackSseEvent(span, evt);
        });
        return pump();
      });
    }
    pump().catch(function (err) {
      markPerf(span, 'stream_monitor_error', { message: String(err && err.message || err) });
      summarizePerf(span, 'stream_monitor_error');
    });
  }

  function monitorNarrationStatusClone(span, response) {
    if (!span || !response || !response.clone) return;
    try {
      response.clone().json().then(function (payload) {
        payload = payload && typeof payload === 'object' ? payload : {};
        markPerf(span, 'narration_status_payload', {
          turn_id: payload.turn_id || '',
          job_status: payload.job && payload.job.status || '',
          has_artifact: !!payload.artifact,
          artifact_text_len: eventVisibleTextLength(payload.artifact || {})
        });
        summarizePerf(span, 'json_complete');
      }).catch(function (err) {
        markPerf(span, 'json_monitor_error', { message: String(err && err.message || err) });
        summarizePerf(span, 'json_monitor_error');
      });
    } catch (err2) {
      markPerf(span, 'json_clone_error', { message: String(err2 && err2.message || err2) });
    }
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

  function recentTurnStreamFetchSeen() {
    if (!activeAt || !lastFetchAt) return false;
    return lastFetchAt >= (activeAt - FETCH_SEEN_GRACE_MS);
  }

  function arm(command) {
    lastCommand = normalizeCommand(command);
    activeAt = Date.now();
    setPending(false);
    window.clearTimeout(timer);
    timer = window.setTimeout(function () {
      if (!activeAt) return;
      if (recentTurnStreamFetchSeen()) {
        log('turn_stream_fetch_already_seen', {
          age_ms: Date.now() - activeAt,
          fetch_delta_ms: lastFetchAt - activeAt,
          session_id: sessionId(),
          command: lastCommand
        });
        return;
      }
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
      var compact = compactUrl(url);
      var isTurnStream = /\/api\/rpg\/session\/turn\/stream(?:$|[?#])/.test(compact);
      var isNarrationStatus = /\/api\/rpg\/session\/narration_status(?:$|[?#])/.test(compact);
      var isActiveRpgFetch = activeAt && /\/api\/rpg\/session\//.test(compact);
      var span = null;
      if (isTurnStream || isNarrationStatus || isActiveRpgFetch) {
        span = startPerfSpan(url, init || {});
      }
      if (isTurnStream) {
        lastFetchAt = Date.now();
        log('turn_stream_fetch_seen', { url: url, age_ms: activeAt ? lastFetchAt - activeAt : 0 });
      }
      return originalFetch.apply(this, arguments).then(function (response) {
        if (span) {
          span.responseHeadersAt = perfNow();
          markPerf(span, 'response_headers', {
            status: response && response.status,
            ok: !!(response && response.ok),
            has_body: !!(response && response.body)
          });
          if (isTurnStream) {
            monitorTurnStreamClone(span, response);
          } else if (isNarrationStatus) {
            monitorNarrationStatusClone(span, response);
          } else {
            summarizePerf(span, 'headers_only');
          }
        }
        return response;
      }).catch(function (error) {
        if (span) {
          markPerf(span, 'fetch_error', { message: String(error && error.message || error) });
          summarizePerf(span, 'fetch_error');
        }
        throw error;
      });
    };
  }

  function init() {
    observeFeed();
    patchFetch();
    log('init', { session_id: sessionId() });
    perfConsole('init', {
      note: 'Turn metrics enabled. Inspect window.__rpgTurnPerfSummaries for recent summaries.'
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
}());