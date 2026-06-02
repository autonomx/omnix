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

  function panelPayloadFromTurnPayload(payload) {
    const root = safeObj(payload);
    const result = safeObj(root.result || root.resolved_result || root);
    return (
      safeObj(root.map_location_panel) ||
      safeObj(result.map_location_panel) ||
      safeObj(safeObj(root.resolved_result).map_location_panel) ||
      safeObj(safeObj(root.narration_context).map_location_panel)
    );
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
      host.appendChild(panel);
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

  function renderMapLocationPanel(payload) {
    const panelPayload = panelPayloadFromTurnPayload(payload);
    if (!Object.keys(panelPayload).length) return false;

    const target = ensurePanelHost();
    const location = safeObj(panelPayload.current_location);
    const exits = safeArr(panelPayload.visible_exits);
    const timeState = safeObj(panelPayload.time_state);
    const source = safeStr(panelPayload.frontend_source || panelPayload.source);
    const name = safeStr(location.name || panelPayload.current_location_id || "Unknown location");
    const description = safeStr(location.description);
    const timeLabel = [
      timeState.day_count ? "Day " + safeStr(timeState.day_count) : "",
      safeStr(timeState.clock_time),
      timeState.time_of_day_label ? "(" + safeStr(timeState.time_of_day_label) + ")" : "",
    ].filter(Boolean).join(" ");

    target.innerHTML = `
      <div class="rpg-map-location-panel" data-source="${escapeHtml(source)}">
        <div class="rpg-map-location-current">
          <div class="rpg-map-location-label">Current location</div>
          <strong>${escapeHtml(name)}</strong>
        </div>
        ${description ? `<p class="rpg-map-location-description">${escapeHtml(description)}</p>` : ""}
        ${timeLabel ? `<div class="rpg-map-location-time">${escapeHtml(timeLabel)}</div>` : ""}
        <div class="rpg-map-location-exits-title">Visible exits</div>
        ${exits.length ? `<ul class="rpg-map-location-exits">${exits.map(renderExit).join("")}</ul>` : `<div class="rpg-map-location-empty">No visible exits.</div>`}
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
