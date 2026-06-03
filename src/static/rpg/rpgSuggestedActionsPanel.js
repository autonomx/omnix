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

  function suggestedActionsPayloadFromTurnPayload(payload) {
    const root = safeObj(payload);
    const result = safeObj(root.result || root.resolved_result || root);
    return firstNonEmptyObj([
      root.suggested_actions_panel,
      result.suggested_actions_panel,
      safeObj(root.resolved_result).suggested_actions_panel,
      safeObj(root.narration_context).suggested_actions_panel,
      root.combat_action_panel,
      result.combat_action_panel,
      root.objective_journal_panel,
      result.objective_journal_panel,
      root.player_hud,
      result.player_hud,
    ]);
  }

  function chromeHelper() {
    return window.RpgPanelChrome || null;
  }

  function ensureSuggestedActionsHost() {
    let panel = document.getElementById("rpgSuggestedActionsPanel");
    const host =
      document.getElementById("rpg-top-panels") ||
      document.querySelector(".rpg-top-panels") ||
      document.getElementById("rpgView") ||
      document.body;

    if (!panel) {
      panel = document.createElement("section");
      panel.id = "rpgSuggestedActionsPanel";
      panel.className = "rpg-suggested-actions-panel";
      const chrome = chromeHelper();
      if (chrome && typeof chrome.decoratePanel === "function") {
        chrome.decoratePanel(panel, "suggested-actions", "deterministic_phase8_suggested_actions_panel");
      } else {
        host.appendChild(panel);
      }
    }

    panel.style.display = "block";
    return panel;
  }

  function normalizeSuggestedActions(payload) {
    payload = safeObj(payload);
    const explicit = safeArr(payload.suggested_actions || payload.actions || payload.recommended_actions);
    const legalActions = safeArr(payload.legal_actions);
    const objectives = safeArr(payload.active_objectives || payload.available_objectives || payload.objectives);
    const actions = [];

    explicit.slice(0, 6).forEach((action, index) => {
      const obj = safeObj(action);
      const command = safeStr(obj.command || obj.value || obj.action || obj.label || `suggestion-${index + 1}`);
      actions.push({
        kind: safeStr(obj.kind || obj.action_type || "suggested"),
        label: safeStr(obj.label || obj.title || command || "Suggested action"),
        command,
        reason: safeStr(obj.reason || obj.summary || obj.detail || "Source-backed suggestion"),
        source: safeStr(obj.source || payload.frontend_source || payload.source || "deterministic_phase8_suggested_actions_panel"),
      });
    });

    legalActions.slice(0, 6).forEach((action, index) => {
      const obj = safeObj(action);
      const actionType = safeStr(obj.action_type || obj.kind || "action");
      const targetId = safeStr(obj.target_id || "");
      const command = targetId ? `${actionType} ${targetId}` : actionType;
      actions.push({
        kind: actionType,
        label: safeStr(obj.label || `Combat ${actionType}`),
        command,
        reason: safeStr(obj.reason || obj.summary || "Legal combat affordance; runtime still validates."),
        source: safeStr(obj.source || payload.frontend_source || payload.source || "deterministic_phase8_suggested_actions_panel"),
      });
    });

    objectives.slice(0, 4).forEach((objective, index) => {
      const obj = safeObj(objective);
      const title = safeStr(obj.title || obj.label || obj.objective_id || `Objective ${index + 1}`);
      actions.push({
        kind: "objective",
        label: title,
        command: safeStr(obj.suggested_command || obj.next_action || title),
        reason: safeStr(obj.summary || obj.status_label || "Objective-driven suggestion"),
        source: safeStr(obj.source || payload.frontend_source || payload.source || "deterministic_phase8_suggested_actions_panel"),
      });
    });

    return actions.slice(0, 8);
  }

  function renderSuggestedAction(action) {
    action = safeObj(action);
    const kind = safeStr(action.kind || "suggested");
    const label = safeStr(action.label || "Suggested action");
    const command = safeStr(action.command || label);
    const reason = safeStr(action.reason || "Source-backed suggestion");
    const source = safeStr(action.source || "deterministic_phase8_suggested_actions_panel");
    return `
      <li class="rpg-suggested-action" data-action-kind="${escapeHtml(kind)}" data-source="${escapeHtml(source)}">
        <strong>${escapeHtml(label)}</strong>
        <code>${escapeHtml(command)}</code>
        <em>${escapeHtml(reason)}</em>
      </li>
    `;
  }

  function renderSuggestedActionsPanel(payload) {
    const panelPayload = suggestedActionsPayloadFromTurnPayload(payload);
    if (!Object.keys(panelPayload).length) return false;

    const target = ensureSuggestedActionsHost();
    const source = safeStr(panelPayload.frontend_source || panelPayload.source || "deterministic_phase8_suggested_actions_panel");
    const actions = normalizeSuggestedActions(panelPayload);
    const chrome = chromeHelper();
    const sourceBadge = chrome && typeof chrome.panelSourceBadge === "function" ? chrome.panelSourceBadge(source, "source-backed") : "";
    const runtimeNotice = chrome && typeof chrome.runtimeValidationNotice === "function" ? chrome.runtimeValidationNotice("Suggestions are not accepted actions until runtime validates the command.") : "<p class=\"rpg-suggested-actions-guidance\">Suggestions are not accepted actions until runtime validates the command.</p>";
    const emptyState = chrome && typeof chrome.panelEmptyState === "function" ? chrome.panelEmptyState("No suggested actions are currently visible.", "Runtime payloads have not supplied objective, legal-action, or recommendation hints yet.") : "<p>No suggested actions are currently visible.</p>";

    if (chrome && typeof chrome.decoratePanel === "function") {
      chrome.decoratePanel(target, "suggested-actions", source);
    }

    target.innerHTML = `
      <div class="rpg-suggested-actions" data-source="${escapeHtml(source)}" data-panel-chrome="deterministic_phase8_panel_chrome">
        <div class="rpg-suggested-actions-header">
          <span>Suggested actions</span>
          ${sourceBadge}
          <em>Read-only command hints from deterministic payloads.</em>
        </div>
        ${runtimeNotice}
        ${actions.length ? `<ol>${actions.map(renderSuggestedAction).join("")}</ol>` : emptyState}
      </div>
    `;
    return true;
  }

  window.RpgSuggestedActionsPanel = {
    render: renderSuggestedActionsPanel,
    suggestedActionsPayloadFromTurnPayload,
    normalizeSuggestedActions,
    renderSuggestedAction,
  };

  const previousInspector = window.RpgLivingWorldInspector;
  if (previousInspector && typeof previousInspector.render === "function") {
    const previousRender = previousInspector.render.bind(previousInspector);
    window.RpgLivingWorldInspector = Object.assign({}, previousInspector, {
      render(payload) {
        renderSuggestedActionsPanel(payload);
        return previousRender(payload);
      },
      renderSuggestedActionsPanel,
    });
  }
})();
