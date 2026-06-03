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

  function panelPayloadFromTurnPayload(payload) {
    const root = safeObj(payload);
    const result = safeObj(root.result || root.resolved_result || root);
    return firstNonEmptyObj([
      root.map_location_panel,
      result.map_location_panel,
      safeObj(root.resolved_result).map_location_panel,
      safeObj(root.narration_context).map_location_panel,
    ]);
  }

  function chromeHelper() {
    return window.RpgPanelChrome || null;
  }

  function ensurePanelHost() {
    let panel = document.getElementById("rpgMinimapPanel");
    const host =
      document.getElementById("rpg-top-panels") ||
      document.querySelector(".rpg-top-panels") ||
      document.getElementById("rpgView") ||
      document.body;

    if (!panel) {
      panel = document.createElement("section");
      panel.id = "rpgMinimapPanel";
      panel.className = "rpg-minimap-panel rpg-map-location-panel-wrapper";
      panel.innerHTML = `
        <div class="rpg-panel-header">
          <span>🗺️ Map</span>
        </div>
        <div class="rpg-panel-content" id="rpgMinimapContent">
          <div class="rpg-minimap" id="rpgMinimap"></div>
        </div>
      `;
      const chrome = chromeHelper();
      if (chrome && typeof chrome.decoratePanel === "function") {
        chrome.decoratePanel(panel, "map-location", "deterministic_phase8_map_location_panel");
      } else {
        host.appendChild(panel);
      }
    }

    let target = document.getElementById("rpgMinimap");
    if (!target) {
      target = document.createElement("div");
      target.id = "rpgMinimap";
      target.className = "rpg-minimap";
      panel.appendChild(target);
    }

    panel.style.display = "block";
    return target;
  }

  function exitDestinationLabel(row) {
    if (row.discovered === true) {
      return safeStr(row.destination_name || row.destination_id || "Unknown destination");
    }
    return "Undiscovered destination";
  }

  function renderExit(row) {
    row = safeObj(row);
    const blocked = row.blocked === true;
    const discovered = row.discovered === true;
    const status = blocked ? "blocked" : (discovered ? "available" : "undiscovered");
    const detail = blocked && row.block_reason ? " — " + safeStr(row.block_reason) : "";
    return `
      <li class="rpg-map-location-exit ${blocked ? "is-blocked" : "is-available"}">
        <span class="rpg-map-location-exit__name">${escapeHtml(safeStr(row.name || row.edge_id || "Exit"))}</span>
        <span class="rpg-map-location-exit__arrow">→</span>
        <span class="rpg-map-location-exit__destination">${escapeHtml(exitDestinationLabel(row))}</span>
        <em class="rpg-map-location-exit__status">${escapeHtml(status + detail)}</em>
      </li>
    `;
  }

  function weatherLabelFromPayload(panelPayload, timeState) {
    const weatherState = safeObj(panelPayload.weather_state);
    const season = safeStr(weatherState.season || timeState.season).replace(/_/g, " ");
    const weather = safeStr(weatherState.weather_label || timeState.weather_label);
    const visibility = safeStr(weatherState.weather_visibility || timeState.weather_visibility);
    return [
      season ? "Season: " + season : "",
      weather ? "Weather: " + weather : "",
      visibility ? "Visibility: " + visibility : "",
    ].filter(Boolean).join(" · ");
  }

  function renderMapLocationPanel(payload) {
    const panelPayload = panelPayloadFromTurnPayload(payload);
    if (!Object.keys(panelPayload).length) return false;

    const target = ensurePanelHost();
    const location = safeObj(panelPayload.current_location);
    const exits = safeArr(panelPayload.visible_exits);
    const timeState = safeObj(panelPayload.time_state);
    const source = safeStr(panelPayload.frontend_source || panelPayload.source || "deterministic_phase8_map_location_panel");
    const chrome = chromeHelper();
    const sourceBadge = chrome && typeof chrome.panelSourceBadge === "function" ? chrome.panelSourceBadge(source, "source-backed") : "";
    const runtimeNotice = chrome && typeof chrome.runtimeValidationNotice === "function" ? chrome.runtimeValidationNotice("Map and location details are read-only; commands still go through runtime validation.") : "<p class=\"rpg-map-location-guidance\">Map and location details are read-only; commands still go through runtime validation.</p>";
    const emptyExits = chrome && typeof chrome.panelEmptyState === "function" ? chrome.panelEmptyState("No visible exits are currently recorded.", "Runtime payloads have not supplied source-backed route details yet.") : "<div class=\"rpg-map-location-empty\">No visible exits.</div>";
    const name = safeStr(location.name || panelPayload.current_location_id || "Unknown location");
    const description = safeStr(location.description);
    const timeLabel = [
      timeState.day_count ? "Day " + safeStr(timeState.day_count) : "",
      safeStr(timeState.clock_time),
      timeState.time_of_day_label ? "(" + safeStr(timeState.time_of_day_label) + ")" : "",
    ].filter(Boolean).join(" ");
    const weatherLabel = weatherLabelFromPayload(panelPayload, timeState);

    if (chrome && typeof chrome.decoratePanel === "function") {
      chrome.decoratePanel(target, "map-location", source);
    }

    target.innerHTML = `
      <div class="rpg-map-location-panel" data-source="${escapeHtml(source)}" data-panel-chrome="deterministic_phase8_panel_chrome">
        <div class="rpg-map-location-header">
          <span>Map & Location</span>
          ${sourceBadge}
          <em>Read-only location, travel, time, weather, and route state from deterministic payloads.</em>
        </div>
        ${runtimeNotice}
        <div class="rpg-map-location-current">
          <div class="rpg-map-location-label">Current location</div>
          <strong>${escapeHtml(name)}</strong>
        </div>
        ${description ? `<p class="rpg-map-location-description">${escapeHtml(description)}</p>` : ""}
        ${timeLabel ? `<div class="rpg-map-location-time">${escapeHtml(timeLabel)}</div>` : ""}
        ${weatherLabel ? `<div class="rpg-map-location-weather">${escapeHtml(weatherLabel)}</div>` : ""}
        <div class="rpg-map-location-exits-title">Visible exits</div>
        ${exits.length ? `<ul class="rpg-map-location-exits">${exits.map(renderExit).join("")}</ul>` : emptyExits}
        <div class="rpg-map-location-source">Source: ${escapeHtml(source)}</div>
      </div>
    `;
    return true;
  }

  window.RpgMapLocationPanel = {
    render: renderMapLocationPanel,
    panelPayloadFromTurnPayload,
  };

  const previousInspector = window.RpgLivingWorldInspector;
  if (previousInspector && typeof previousInspector.render === "function") {
    const previousRender = previousInspector.render.bind(previousInspector);
    window.RpgLivingWorldInspector = Object.assign({}, previousInspector, {
      render(payload) {
        renderMapLocationPanel(payload);
        return previousRender(payload);
      },
      renderMapLocationPanel,
    });
  }
})();