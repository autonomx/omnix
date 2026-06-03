(function () {
  "use strict";

  const SOURCE = "deterministic_phase8_panel_chrome";

  function safeStr(value) {
    return value == null ? "" : String(value);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;");
  }

  function panelSourceBadge(source, label) {
    const safeSource = safeStr(source || SOURCE);
    const safeLabel = safeStr(label || "source-backed");
    return `<span class="rpg-panel-source-badge" data-source="${escapeHtml(safeSource)}">${escapeHtml(safeLabel)}</span>`;
  }

  function panelEmptyState(message, detail) {
    const safeMessage = safeStr(message || "No source-backed entries are currently visible.");
    const safeDetail = safeStr(detail || "This panel is read-only and will update when deterministic runtime payloads include data.");
    return `
      <p class="rpg-panel-empty-state" data-source="${escapeHtml(SOURCE)}">
        <strong>${escapeHtml(safeMessage)}</strong>
        <span>${escapeHtml(safeDetail)}</span>
      </p>
    `;
  }

  function runtimeValidationNotice(message) {
    const safeMessage = safeStr(message || "Panel content is advisory; commands still require runtime validation.");
    return `<p class="rpg-panel-runtime-notice" data-source="${escapeHtml(SOURCE)}">${escapeHtml(safeMessage)}</p>`;
  }

  function attachPanelToLayout(panelElement, panelId) {
    if (!panelElement || !panelId) return panelElement || null;
    const registry = window.RpgPanelLayoutRegistry;
    if (registry && typeof registry.attachPanelToSlot === "function") {
      return registry.attachPanelToSlot(panelElement, panelId);
    }
    panelElement.setAttribute("data-layout-slot", safeStr(panelId));
    panelElement.setAttribute("data-layout-source", SOURCE);
    return panelElement;
  }

  function decoratePanel(panelElement, panelId, source) {
    const attached = attachPanelToLayout(panelElement, panelId);
    if (!attached) return null;
    attached.setAttribute("data-panel-chrome-source", SOURCE);
    attached.setAttribute("data-panel-payload-source", safeStr(source || SOURCE));
    return attached;
  }

  window.RpgPanelChrome = {
    SOURCE,
    escapeHtml,
    panelSourceBadge,
    panelEmptyState,
    runtimeValidationNotice,
    attachPanelToLayout,
    decoratePanel,
  };
})();
