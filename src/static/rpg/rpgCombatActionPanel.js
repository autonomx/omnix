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
      host.appendChild(panel);
    }

    panel.style.display = "block";
    return panel;
  }

  function renderParticipant(participant) {
    participant = safeObj(participant);
    const actorId = safeStr(participant.actor_id);
    const name = safeStr(participant.name || actorId || "Actor");
    const hp = safeStr(participant.hp ?? "");
    const maxHp = safeStr(participant.max_hp ?? "");
    const side = safeStr(participant.side || "unknown");
    const defeated = participant.defeated === true ? "Defeated" : "Ready";
    return `
      <li class="rpg-combat-participant is-${escapeHtml(side)}">
        <strong>${escapeHtml(name)}</strong>
        <span>${escapeHtml(side)}</span>
        <em>${escapeHtml(hp)}${maxHp ? `/${escapeHtml(maxHp)}` : ""} HP</em>
        <small>${escapeHtml(defeated)}</small>
      </li>
    `;
  }

  function renderAction(action) {
    action = safeObj(action);
    const label = safeStr(action.label || action.action_type || "Action");
    const target = safeStr(action.target_id || "");
    const disabled = action.enabled === false ? " disabled" : "";
    return `
      <li class="rpg-combat-action-affordance${disabled}">
        <span>${escapeHtml(label)}</span>
        ${target ? `<em>${escapeHtml(target)}</em>` : ""}
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
    const source = safeStr(panelPayload.frontend_source || panelPayload.source);
    const participants = safeArr(panelPayload.participants);
    const legalActions = safeArr(panelPayload.legal_actions);
    const warnings = safeArr(panelPayload.major_warnings);
    const currentActorId = safeStr(panelPayload.current_actor_id || "none");
    const statusLabel = safeStr(panelPayload.status_label || (panelPayload.active ? "In combat" : "Not in combat"));
    const turnLabel = panelPayload.is_player_turn === true ? "Player turn" : "Waiting";

    target.innerHTML = `
      <div class="rpg-combat-action" data-source="${escapeHtml(source)}">
        <div class="rpg-combat-action-header">
          <span>Combat</span>
          <em>Source: ${escapeHtml(source)}</em>
        </div>
        <section class="rpg-combat-status">
          <strong>${escapeHtml(statusLabel)}</strong>
          <span>${escapeHtml(turnLabel)}</span>
          <em>Current actor: ${escapeHtml(currentActorId)}</em>
        </section>
        <section class="rpg-combat-participants">
          <h4>Participants</h4>
          ${participants.length ? `<ul>${participants.map(renderParticipant).join("")}</ul>` : "<p>No combat participants recorded.</p>"}
        </section>
        <section class="rpg-combat-actions">
          <h4>Legal action affordances</h4>
          ${legalActions.length ? `<ul>${legalActions.map(renderAction).join("")}</ul>` : "<p>No legal player combat actions are currently available.</p>"}
        </section>
        ${warnings.length ? `<ul class="rpg-combat-warnings">${warnings.map(renderWarning).join("")}</ul>` : ""}
      </div>
    `;
    return true;
  }

  window.RpgCombatActionPanel = {
    render: renderCombatActionPanel,
    combatActionPayloadFromTurnPayload,
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
