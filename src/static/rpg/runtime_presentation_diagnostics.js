// N117.1 — Runtime presentation diagnostics inspector bridge.
// Additive UI helper: renders diagnostics when API/SSE payloads expose
// runtime_presentation_diagnostics or presentation_debug.
(function () {
  'use strict';

  function safeObj(value) {
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  }

  function safeStr(value) {
    return value == null ? '' : String(value);
  }

  function escapeHtml(value) {
    return safeStr(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function prettyJson(value) {
    try {
      return JSON.stringify(value == null ? {} : value, null, 2);
    } catch (_err) {
      return safeStr(value);
    }
  }

  function ensurePanel() {
    var panel = document.getElementById('runtime-presentation-diagnostics-panel');
    if (panel) return panel;
    var host = document.getElementById('rpg-inspector-panel') ||
      document.getElementById('rpg-debug-panel') ||
      document.getElementById('rpg-top-panels') ||
      document.body;
    panel = document.createElement('section');
    panel.id = 'runtime-presentation-diagnostics-panel';
    panel.className = 'runtime-presentation-diagnostics-panel rpg-debug-card';
    panel.innerHTML = '' +
      '<details open>' +
        '<summary>Runtime Presentation Diagnostics</summary>' +
        '<div class="rpg-debug-muted">No runtime presentation diagnostics yet.</div>' +
      '</details>';
    host.appendChild(panel);
    return panel;
  }

  function renderSection(title, value, open) {
    var json = prettyJson(value || {});
    return '' +
      '<details ' + (open ? 'open' : '') + '>' +
        '<summary>' + escapeHtml(title) + '</summary>' +
        '<pre class="rpg-runtime-diagnostics-json">' + escapeHtml(json) + '</pre>' +
      '</details>';
  }

  function renderDiagnostics(payload) {
    var diagnostics = safeObj(payload && (payload.runtime_presentation_diagnostics || payload.presentation_debug || payload));
    var panel = ensurePanel();
    if (!diagnostics.presentation_debug_available && !diagnostics.current_turn_prompt_contract && !diagnostics.npc_response_architecture) {
      panel.innerHTML = '' +
        '<details open>' +
          '<summary>Runtime Presentation Diagnostics</summary>' +
          '<div class="rpg-debug-muted">No runtime presentation diagnostics available on this payload.</div>' +
        '</details>';
      return;
    }
    var statusBits = [];
    if (diagnostics.turn_id) statusBits.push('turn ' + diagnostics.turn_id);
    if (diagnostics.fallback_source) statusBits.push('fallback=' + diagnostics.fallback_source);
    if (diagnostics.has_prompt_contract) statusBits.push('prompt contract');
    if (diagnostics.has_npc_response_architecture) statusBits.push('npc architecture');
    panel.innerHTML = '' +
      '<details open>' +
        '<summary>Runtime Presentation Diagnostics</summary>' +
        '<div class="rpg-debug-muted">' + escapeHtml(statusBits.join(' · ') || 'runtime diagnostics') + '</div>' +
        renderSection('Current-turn prompt contract', diagnostics.current_turn_prompt_contract, true) +
        renderSection('NPC response architecture', diagnostics.npc_response_architecture, false) +
        renderSection('Provider / fallback status', diagnostics.provider_payload_status, false) +
        renderSection('Grounding guardrails', diagnostics.grounding_guardrails, false) +
        renderSection('Unsupported combat claim guard', diagnostics.unsupported_combat_claim_guard, false) +
        renderSection('Service / economy veto', diagnostics.service_economy_veto, false) +
      '</details>';
  }

  function extractDiagnosticsFromEvent(detail) {
    detail = safeObj(detail);
    var direct = safeObj(detail.runtime_presentation_diagnostics || detail.presentation_debug);
    if (Object.keys(direct).length) return direct;
    var artifact = safeObj(detail.artifact);
    direct = safeObj(artifact.runtime_presentation_diagnostics || artifact.presentation_debug);
    if (Object.keys(direct).length) return direct;
    var patch = safeObj(detail.patch);
    direct = safeObj(patch.runtime_presentation_diagnostics || patch.presentation_debug);
    return direct;
  }

  window.RPGRuntimePresentationDiagnostics = {
    render: renderDiagnostics,
    ensurePanel: ensurePanel
  };

  window.addEventListener('rpg:presentation_diagnostics', function (event) {
    renderDiagnostics(safeObj(event.detail));
  });

  window.addEventListener('rpg:sse_diagnostic', function (event) {
    var diagnostics = extractDiagnosticsFromEvent(event.detail);
    if (Object.keys(diagnostics).length) renderDiagnostics(diagnostics);
  });

  document.addEventListener('DOMContentLoaded', function () {
    ensurePanel();
  });
}());
