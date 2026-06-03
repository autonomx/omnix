(function () {
  "use strict";

  function safeObj(value) {
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  }

  function safeArr(value) {
    return Array.isArray(value) ? value : [];
  }

  function safeStr(value) {
    return value == null ? "" : String(value);
  }

  function escapeHtml(value) {
    const chrome = window.RpgPanelChrome;
    if (chrome && typeof chrome.escapeHtml === "function") return chrome.escapeHtml(value);
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;");
  }

  function firstNonEmptyObj(values) {
    for (const value of values) {
      const candidate = safeObj(value);
      if (Object.keys(candidate).length) return candidate;
    }
    return {};
  }

  function recentActivityPayloadFromTurnPayload(payload) {
    const root = safeObj(payload);
    const result = safeObj(root.result || root.resolved_result || root);
    return firstNonEmptyObj([
      root.recent_activity_panel,
      result.recent_activity_panel,
      safeObj(root.resolved_result).recent_activity_panel,
      safeObj(root.narration_context).recent_activity_panel,
      root.objective_journal_panel,
      result.objective_journal_panel,
      root.combat_action_panel,
      result.combat_action_panel,
      root.player_hud,
      result.player_hud,
    ]);
  }

  function chromeHelper() {
    return window.RpgPanelChrome || null;
  }

  function ensureRecentActivityHost() {
    let panel = document.getElementById("rpgRecentActivityPanel");
    const host =
      document.getElementById("rpg-top-panels") ||
      document.querySelector(".rpg-top-panels") ||
      document.getElementById("rpgView") ||
      document.body;

    if (!panel) {
      panel = document.createElement("section");
      panel.id = "rpgRecentActivityPanel";
      panel.className = "rpg-recent-activity-panel";
      const chrome = chromeHelper();
      if (chrome && typeof chrome.decoratePanel === "function") {
        chrome.decoratePanel(panel, "recent-activity", "deterministic_phase8_recent_activity_panel");
      } else {
        host.appendChild(panel);
      }
    }

    panel.style.display = "block";
    return panel;
  }

  function normalizeActivityEntries(payload) {
    payload = safeObj(payload);
    const recentAction = safeObj(payload.recent_action_state || payload.action_state);
    const journalEntries = safeArr(payload.journal_entries || payload.recent_journal_entries);
    const worldEvents = safeArr(payload.world_events || payload.recent_world_events || payload.location_events);
    const warnings = safeArr(payload.major_warnings || payload.warnings);
    const entries = [];

    if (Object.keys(recentAction).length) {
      entries.push({
        kind: safeStr(recentAction.kind || recentAction.action || "recent_action"),
        label: safeStr(recentAction.label || recentAction.summary || recentAction.status || "Recent action recorded"),
        detail: safeStr(recentAction.detail || recentAction.reason || recentAction.command || "Runtime action state"),
        severity: safeStr(recentAction.severity || "info"),
      });
    }

    journalEntries.slice(0, 5).forEach((entry, index) => {
      const obj = safeObj(entry);
      entries.push({
        kind: safeStr(obj.kind || obj.category || "journal"),
        label: safeStr(obj.title || obj.label || obj.summary || `Journal entry ${index + 1}`),
        detail: safeStr(obj.detail || obj.text || obj.description || "Journal update"),
        severity: safeStr(obj.severity || "info"),
      });
    });

    worldEvents.slice(0, 5).forEach((event, index) => {
      const obj = safeObj(event);
      entries.push({
        kind: safeStr(obj.kind || obj.type || "world_event"),
        label: safeStr(obj.title || obj.label || obj.summary || `World event ${index + 1}`),
        detail: safeStr(obj.detail || obj.description || obj.location || "World signal"),
        severity: safeStr(obj.severity || "info"),
      });
    });

    warnings.slice(0, 5).forEach((warning, index) => {
      const obj = safeObj(warning);
      entries.push({
        kind: safeStr(obj.kind || "warning"),
        label: safeStr(obj.label || obj.summary || `Warning ${index + 1}`),
        detail: safeStr(obj.detail || obj.reason || "Source-backed warning"),
        severity: safeStr(obj.severity || "warning"),
      });
    });

    return entries.slice(0, 8);
  }

  function renderActivityEntry(entry) {
    entry = safeObj(entry);
    const kind = safeStr(entry.kind || "activity");
    const label = safeStr(entry.label || "Activity");
    const detail = safeStr(entry.detail || "Source-backed runtime update");
    const severity = safeStr(entry.severity || "info");
    return `
      <li class="rpg-recent-activity-entry is-${escapeHtml(severity)}" data-activity-kind="${escapeHtml(kind)}">
        <strong>${escapeHtml(label)}</strong>
        <span>${escapeHtml(kind).replace(/_/g, " ")}</span>
        <em>${escapeHtml(detail)}</em>
      </li>
    `;
  }

  function renderRecentActivityPanel(payload) {
    const panelPayload = recentActivityPayloadFromTurnPayload(payload);
    if (!Object.keys(panelPayload).length) return false;

    const target = ensureRecentActivityHost();
    const source = safeStr(panelPayload.frontend_source || panelPayload.source || "deterministic_phase8_recent_activity_panel");
    const entries = normalizeActivityEntries(panelPayload);
    const chrome = chromeHelper();
    const sourceBadge = chrome && typeof chrome.panelSourceBadge === "function" ? chrome.panelSourceBadge(source, "source-backed") : "";
    const runtimeNotice = chrome && typeof chrome.runtimeValidationNotice === "function" ? chrome.runtimeValidationNotice("Recent activity is context only; commands still go through runtime validation.") : "<p class=\"rpg-recent-activity-guidance\">Use this as context only; commands still go through runtime validation.</p>";
    const emptyState = chrome && typeof chrome.panelEmptyState === "function" ? chrome.panelEmptyState("No recent activity is currently visible.", "Runtime, journal, warning, and world-event payloads have not supplied entries yet.") : "<p>No recent activity is currently visible.</p>";

    if (chrome && typeof chrome.decoratePanel === "function") {
      chrome.decoratePanel(target, "recent-activity", source);
    }

    target.innerHTML = `
      <div class="rpg-recent-activity" data-source="${escapeHtml(source)}" data-panel-chrome="deterministic_phase8_panel_chrome">
        <div class="rpg-recent-activity-header">
          <span>Recent activity</span>
          ${sourceBadge}
          <em>Read-only world, journal, warning, and action signals from deterministic payloads.</em>
        </div>
        ${runtimeNotice}
        ${entries.length ? `<ol>${entries.map(renderActivityEntry).join("")}</ol>` : emptyState}
      </div>
    `;
    return true;
  }

  window.RpgRecentActivityPanel = {
    render: renderRecentActivityPanel,
    recentActivityPayloadFromTurnPayload,
    normalizeActivityEntries,
    renderActivityEntry,
  };

  const previousInspector = window.RpgLivingWorldInspector;
  if (previousInspector && typeof previousInspector.render === "function") {
    const previousRender = previousInspector.render.bind(previousInspector);
    window.RpgLivingWorldInspector = Object.assign({}, previousInspector, {
      render(payload) {
        renderRecentActivityPanel(payload);
        return previousRender(payload);
      },
      renderRecentActivityPanel,
    });
  }
})();
