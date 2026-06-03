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
      .replace(/"/g, "&quot;");
  }

  function firstNonEmptyObj(values) {
    for (const value of values) {
      const candidate = safeObj(value);
      if (Object.keys(candidate).length) return candidate;
    }
    return {};
  }

  function combatActionPayloadFromTurnPayload(payload) {
    const root = safeObj(payload);
    const result = safeObj(root.result || root.resolved_result || root);
    return firstNonEmptyObj([
      root.combat_action_panel,
      result.combat_action_panel,
      safeObj(root.resolved_result).combat_action_panel,
      safeObj(root.narration_context).combat_action_panel,
    ]);
  }

  function chromeHelper() {
    return window.RpgPanelChrome || null;
  }

  function ensureCombatActionHost() {
    let panel = document.getElementById("rpgCombatActionPanel");
    const host =
      document.getElementById("rpg-top-panels") ||
      document.querySelector(".rpg-top-panels") ||
      document.getElementById("rpgView") ||
      document.body;

    if (!panel) {
      panel = document.createElement("section");
      panel.id = "rpgCombatActionPanel";
      panel.className = "rpg-combat-action-panel";
      const chrome = chromeHelper();
      if (chrome && typeof chrome.decoratePanel === "function") {
        chrome.decoratePanel(panel, "combat-action", "deterministic_phase8_combat_action_panel");
      } else {
        host.appendChild(panel);
      }
    }

    panel.style.display = "block";
    return panel;
  }

  function healthPercent(participant) {
    participant = safeObj(participant);
    const hp = Number(participant.hp || 0);
    const maxHp = Number(participant.max_hp || participant.hp || 0);
    if (!Number.isFinite(hp) || !Number.isFinite(maxHp) || maxHp <= 0) return 0;
    return Math.max(0, Math.min(100, Math.round((hp / maxHp) * 100)));
  }

  function participantStateLabel(participant) {
    participant = safeObj(participant);
    if (participant.defeated === true) return "Defeated";
    const percent = healthPercent(participant);
    if (percent <= 25) return "Critical";
    if (percent <= 50) return "Wounded";
    return "Ready";
  }

  function targetThreatLabel(target) {
    target = safeObj(target);
    if (target.defeated === true) return "Defeated target";
    const percent = healthPercent(target);
    if (percent <= 25) return "Near defeat";
    if (percent <= 50) return "Wounded target";
    return "Active target";
  }

  function actionCommand(action) {
    action = safeObj(action);
    const actionType = safeStr(action.action_type || "action").trim() || "action";
    const target = safeStr(action.target_id).trim();
    return target ? `${actionType} ${target}` : actionType;
  }

  function turnGuidance(panelPayload) {
    panelPayload = safeObj(panelPayload);
    if (panelPayload.active !== true) {
      return "No active combat. Continue exploring or pursue your current objective.";
    }
    if (panelPayload.is_player_turn === true) {
      const count = safeArr(panelPayload.legal_actions).length;
      return count
        ? "Choose a listed combat action; the runtime still validates the command."
        : "It is your turn, but no deterministic combat actions are currently available.";
    }
    const current = safeStr(panelPayload.current_actor_id || "another combatant");
    return `Waiting for ${current}; player combat commands should not be treated as accepted yet.`;
  }

  function renderParticipant(participant) {
    participant = safeObj(participant);
    const actorId = safeStr(participant.actor_id);
    const name = safeStr(participant.name || actorId || "Actor");
    const hp = safeStr(participant.hp ?? "");
    const maxHp = safeStr(participant.max_hp ?? "");
    const side = safeStr(participant.side || "unknown");
    const stateLabel = participantStateLabel(participant);
    const percent = healthPercent(participant);
    return `
      <li class="rpg-combat-participant is-${escapeHtml(side)}" data-actor-id="${escapeHtml(actorId)}">
        <div class="rpg-combat-participant-main">
          <strong>${escapeHtml(name)}</strong>
          <span>${escapeHtml(side)}</span>
        </div>
        <div class="rpg-combat-health" aria-label="${escapeHtml(name)} health ${escapeHtml(percent)} percent">
          <span class="rpg-combat-health-bar" style="width: ${escapeHtml(percent)}%"></span>
        </div>
        <em>${escapeHtml(hp)}${maxHp ? `/${escapeHtml(maxHp)}` : ""} HP</em>
        <small>${escapeHtml(stateLabel)}</small>
      </li>
    `;
  }

  function renderTarget(target) {
    target = safeObj(target);
    const actorId = safeStr(target.actor_id);
    const name = safeStr(target.name || actorId || "Target");
    return `
      <li class="rpg-combat-target" data-target-id="${escapeHtml(actorId)}">
        <strong>${escapeHtml(name)}</strong>
        <span>${escapeHtml(targetThreatLabel(target))}</span>
        <em>${escapeHtml(healthPercent(target))}% HP</em>
      </li>
    `;
  }

  function renderAction(action) {
    action = safeObj(action);
    const label = safeStr(action.label || action.action_type || "Action");
    const target = safeStr(action.target_id || "");
    const disabled = action.enabled === false ? " disabled" : "";
    const command = actionCommand(action);
    return `
      <li class="rpg-combat-action-affordance${disabled}" data-action-type="${escapeHtml(action.action_type || "action")}">
        <span>${escapeHtml(label)}</span>
        ${target ? `<em>${escapeHtml(target)}</em>` : ""}
        <code class="rpg-combat-action-command">${escapeHtml(command)}</code>
      </li>
    `;
  }

  function renderWarning(warning) {
    warning = safeObj(warning);
    const severity = safeStr(warning.severity || "info");
    const label = safeStr(warning.label || warning.kind || "Combat warning");
    return `<li class="rpg-combat-warning is-${escapeHtml(severity)}">${escapeHtml(label)}</li>`;
  }

  function renderCombatActionPanel(payload) {
    const panelPayload = combatActionPayloadFromTurnPayload(payload);
    if (!Object.keys(panelPayload).length) return false;

    const target = ensureCombatActionHost();
    const source = safeStr(panelPayload.frontend_source || panelPayload.source || "deterministic_phase8_combat_action_panel");
    const participants = safeArr(panelPayload.participants);
    const legalActions = safeArr(panelPayload.legal_actions);
    const targets = safeArr(panelPayload.target_summary);
    const warnings = safeArr(panelPayload.major_warnings);
    const currentActorId = safeStr(panelPayload.current_actor_id || "none");
    const statusLabel = safeStr(panelPayload.status_label || (panelPayload.active ? "In combat" : "Not in combat"));
    const turnLabel = panelPayload.is_player_turn === true ? "Player turn" : "Waiting";
    const guidance = turnGuidance(panelPayload);
    const chrome = chromeHelper();
    const sourceBadge = chrome && typeof chrome.panelSourceBadge === "function" ? chrome.panelSourceBadge(source, "source-backed") : "";
    const runtimeNotice = chrome && typeof chrome.runtimeValidationNotice === "function" ? chrome.runtimeValidationNotice("Combat action affordances are read-only; commands still go through runtime validation.") : "<p class=\"rpg-combat-action-guidance\">Combat action affordances are read-only; commands still go through runtime validation.</p>";
    const emptyParticipants = chrome && typeof chrome.panelEmptyState === "function" ? chrome.panelEmptyState("No combat participants are currently visible.", "Runtime payloads have not supplied source-backed combat participants yet.") : "<p>No combat participants recorded.</p>";
    const emptyTargets = chrome && typeof chrome.panelEmptyState === "function" ? chrome.panelEmptyState("No target summary is currently available.", "Runtime payloads have not supplied source-backed target information yet.") : "<p>No target summary is currently available.</p>";
    const emptyActions = chrome && typeof chrome.panelEmptyState === "function" ? chrome.panelEmptyState("No legal player combat actions are currently available.", "Runtime payloads have not supplied source-backed legal combat actions yet.") : "<p>No legal player combat actions are currently available.</p>";

    if (chrome && typeof chrome.decoratePanel === "function") {
      chrome.decoratePanel(target, "combat-action", source);
    }

    target.innerHTML = `
      <div class="rpg-combat-action" data-source="${escapeHtml(source)}" data-active="${panelPayload.active === true ? "true" : "false"}" data-panel-chrome="deterministic_phase8_panel_chrome">
        <div class="rpg-combat-action-header">
          <span>Combat</span>
          ${sourceBadge}
          <em>Read-only combat state and action affordances from deterministic runtime payloads.</em>
        </div>
        <section class="rpg-combat-status">
          <strong>${escapeHtml(statusLabel)}</strong>
          <span>${escapeHtml(turnLabel)}</span>
          <em>Current actor: ${escapeHtml(currentActorId)}</em>
        </section>
        ${runtimeNotice}
        <p class="rpg-combat-turn-guidance">${escapeHtml(guidance)}</p>
        <section class="rpg-combat-participants">
          <h4>Participants</h4>
          ${participants.length ? `<ul>${participants.map(renderParticipant).join("")}</ul>` : emptyParticipants}
        </section>
        <section class="rpg-combat-targets">
          <h4>Targets</h4>
          ${targets.length ? `<ul>${targets.map(renderTarget).join("")}</ul>` : emptyTargets}
        </section>
        <section class="rpg-combat-actions">
          <h4>Legal action affordances</h4>
          ${legalActions.length ? `<ul>${legalActions.map(renderAction).join("")}</ul>` : emptyActions}
        </section>
        ${warnings.length ? `<ul class="rpg-combat-warnings">${warnings.map(renderWarning).join("")}</ul>` : ""}
      </div>
    `;
    return true;
  }

  window.RpgCombatActionPanel = {
    render: renderCombatActionPanel,
    combatActionPayloadFromTurnPayload,
    healthPercent,
    participantStateLabel,
    targetThreatLabel,
    actionCommand,
    turnGuidance,
  };

  const previousInspector = window.RpgLivingWorldInspector;
  if (previousInspector && typeof previousInspector.render === "function") {
    const previousRender = previousInspector.render.bind(previousInspector);
    window.RpgLivingWorldInspector = Object.assign({}, previousInspector, {
      render(payload) {
        renderCombatActionPanel(payload);
        return previousRender(payload);
      },
      renderCombatActionPanel,
    });
  }
})();