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

  function hudPayloadFromTurnPayload(payload) {
    const root = safeObj(payload);
    const result = safeObj(root.result || root.resolved_result || root);
    return firstNonEmptyObj([
      root.player_hud,
      result.player_hud,
      safeObj(root.resolved_result).player_hud,
      safeObj(root.narration_context).player_hud,
    ]);
  }

  function chromeHelper() {
    return window.RpgPanelChrome || null;
  }

  function ensureHudHost() {
    let panel = document.getElementById("rpgPlayerHudPanel");
    const host =
      document.getElementById("rpg-top-panels") ||
      document.querySelector(".rpg-top-panels") ||
      document.getElementById("rpgView") ||
      document.body;

    if (!panel) {
      panel = document.createElement("section");
      panel.id = "rpgPlayerHudPanel";
      panel.className = "rpg-player-hud-panel";
      const chrome = chromeHelper();
      if (chrome && typeof chrome.decoratePanel === "function") {
        chrome.decoratePanel(panel, "player-hud", "deterministic_phase8_player_hud_panel");
      } else {
        host.insertBefore(panel, host.firstChild || null);
      }
    }

    panel.style.display = "block";
    return panel;
  }

  function renderItem(item) {
    item = safeObj(item);
    const name = safeStr(item.name || item.item_id || "Item");
    const qty = safeStr(item.qty || 1);
    return `<li class="rpg-player-hud-item">${escapeHtml(name)} <span>x${escapeHtml(qty)}</span></li>`;
  }

  function renderPartyMember(member) {
    member = safeObj(member);
    const name = safeStr(member.name || member.id || "Companion");
    const role = safeStr(member.role || "companion");
    return `<li class="rpg-player-hud-party-member">${escapeHtml(name)} <span>${escapeHtml(role)}</span></li>`;
  }

  function renderWarning(warning) {
    warning = safeObj(warning);
    const severity = safeStr(warning.severity || "info");
    const label = safeStr(warning.label || warning.kind || "Warning");
    return `<li class="rpg-player-hud-warning is-${escapeHtml(severity)}">${escapeHtml(label)}</li>`;
  }

  function renderPlayerHud(payload) {
    const hud = hudPayloadFromTurnPayload(payload);
    if (!Object.keys(hud).length) return false;

    const target = ensureHudHost();
    const location = safeObj(hud.current_location);
    const objective = safeObj(hud.active_objective);
    const resources = safeObj(hud.player_resources);
    const currency = safeObj(resources.currency);
    const party = safeObj(hud.party_summary);
    const timeState = safeObj(hud.time_state);
    const warnings = safeArr(hud.major_warnings);
    const source = safeStr(hud.frontend_source || hud.source || "deterministic_phase8_player_hud_panel");
    const chrome = chromeHelper();
    const sourceBadge = chrome && typeof chrome.panelSourceBadge === "function" ? chrome.panelSourceBadge(source, "source-backed") : "";
    const runtimeNotice = chrome && typeof chrome.runtimeValidationNotice === "function" ? chrome.runtimeValidationNotice("Player HUD details are read-only; commands still go through runtime validation.") : "<p class=\"rpg-player-hud-guidance\">Player HUD details are read-only; commands still go through runtime validation.</p>";
    const emptyItems = chrome && typeof chrome.panelEmptyState === "function" ? chrome.panelEmptyState("No visible items are currently recorded.", "Runtime payloads have not supplied source-backed player inventory details yet.") : "<div class=\"rpg-player-hud-empty\">No visible items.</div>";
    const emptyParty = chrome && typeof chrome.panelEmptyState === "function" ? chrome.panelEmptyState("No companions are currently visible.", "Runtime payloads have not supplied source-backed party details yet.") : "<div class=\"rpg-player-hud-empty\">No companions.</div>";
    const locationName = safeStr(location.name || hud.current_location_id || "Unknown location");
    const objectiveTitle = safeStr(objective.title || "No active objective recorded");
    const weatherLabel = [
      timeState.season ? "Season: " + safeStr(timeState.season).replace(/_/g, " ") : "",
      timeState.weather_label ? "Weather: " + safeStr(timeState.weather_label) : "",
    ].filter(Boolean).join(" · ");

    if (chrome && typeof chrome.decoratePanel === "function") {
      chrome.decoratePanel(target, "player-hud", source);
    }

    target.innerHTML = `
      <div class="rpg-player-hud" data-source="${escapeHtml(source)}" data-panel-chrome="deterministic_phase8_panel_chrome">
        <div class="rpg-player-hud-header">
          <span>Player HUD</span>
          ${sourceBadge}
          <em>Read-only player, location, objective, resource, and party state from deterministic payloads.</em>
        </div>
        ${runtimeNotice}
        <div class="rpg-player-hud-row">
          <div class="rpg-player-hud-card rpg-player-hud-location">
            <span class="rpg-player-hud-label">Location</span>
            <strong>${escapeHtml(locationName)}</strong>
          </div>
          <div class="rpg-player-hud-card rpg-player-hud-objective">
            <span class="rpg-player-hud-label">Active objective</span>
            <strong>${escapeHtml(objectiveTitle)}</strong>
            ${objective.status ? `<em>${escapeHtml(objective.status)}</em>` : ""}
          </div>
        </div>
        <div class="rpg-player-hud-row">
          <div class="rpg-player-hud-card rpg-player-hud-resources">
            <span class="rpg-player-hud-label">Resources</span>
            <div class="rpg-player-hud-currency">${escapeHtml(currency.gold || 0)}g ${escapeHtml(currency.silver || 0)}s ${escapeHtml(currency.copper || 0)}c</div>
            ${safeArr(resources.items).length ? `<ul>${safeArr(resources.items).map(renderItem).join("")}</ul>` : emptyItems}
          </div>
          <div class="rpg-player-hud-card rpg-player-hud-party">
            <span class="rpg-player-hud-label">Party</span>
            ${safeArr(party.members).length ? `<ul>${safeArr(party.members).map(renderPartyMember).join("")}</ul>` : emptyParty}
          </div>
        </div>
        ${weatherLabel ? `<div class="rpg-player-hud-weather">${escapeHtml(weatherLabel)}</div>` : ""}
        ${warnings.length ? `<ul class="rpg-player-hud-warnings">${warnings.map(renderWarning).join("")}</ul>` : ""}
      </div>
    `;
    return true;
  }

  window.RpgPlayerHud = {
    render: renderPlayerHud,
    hudPayloadFromTurnPayload,
  };

  const previousInspector = window.RpgLivingWorldInspector;
  if (previousInspector && typeof previousInspector.render === "function") {
    const previousRender = previousInspector.render.bind(previousInspector);
    window.RpgLivingWorldInspector = Object.assign({}, previousInspector, {
      render(payload) {
        renderPlayerHud(payload);
        return previousRender(payload);
      },
      renderPlayerHud,
    });
  }
})();