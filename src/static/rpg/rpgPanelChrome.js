(function () {
  "use strict";

  const SOURCE = "deterministic_phase8_panel_chrome";
  const PANEL_STATES = {
    advisory: "advisory",
    empty: "empty",
    ready: "ready",
    source_backed: "source_backed",
  };

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

  function panelChromeLabel(panelId, fallbackLabel) {
    const registry = window.RpgPanelLayoutRegistry;
    if (registry && typeof registry.panelLabel === "function") {
      const registryLabel = registry.panelLabel(panelId);
      if (registryLabel) return safeStr(registryLabel);
    }
    return safeStr(fallbackLabel || "RPG panel");
  }

  function panelChromeA11yAttrs(panelId, fallbackLabel) {
    const label = panelChromeLabel(panelId, fallbackLabel);
    return `role="region" aria-label="${escapeHtml(label)}" data-panel-a11y-source="${escapeHtml(SOURCE)}"`;
  }

  function panelChromeState(state) {
    const safeState = safeStr(state || PANEL_STATES.source_backed).toLowerCase().replace(/-/g, "_");
    return Object.prototype.hasOwnProperty.call(PANEL_STATES, safeState) ? PANEL_STATES[safeState] : PANEL_STATES.source_backed;
  }

  function panelStateAttrs(state) {
    const safeState = panelChromeState(state);
    return `data-panel-state="${escapeHtml(safeState)}" data-panel-state-source="${escapeHtml(SOURCE)}"`;
  }

  function applyPanelState(panelElement, state) {
    if (!panelElement) return null;
    const safeState = panelChromeState(state);
    panelElement.setAttribute("data-panel-state", safeState);
    panelElement.setAttribute("data-panel-state-source", SOURCE);
    return panelElement;
  }

  function panelSourceBadge(source, label) {
    const safeSource = safeStr(source || SOURCE);
    const safeLabel = safeStr(label || "source-backed");
    return `<span class="rpg-panel-source-badge" data-source="${escapeHtml(safeSource)}" ${panelStateAttrs("source_backed")} role="note" aria-label="Panel source: ${escapeHtml(safeLabel)}">${escapeHtml(safeLabel)}</span>`;
  }

  function panelEmptyState(message, detail) {
    const safeMessage = safeStr(message || "No source-backed entries are currently visible.");
    const safeDetail = safeStr(detail || "This panel is read-only and will update when deterministic runtime payloads include data.");
    return `
      <p class="rpg-panel-empty-state" data-source="${escapeHtml(SOURCE)}" ${panelStateAttrs("empty")} role="status" aria-live="polite">
        <strong>${escapeHtml(safeMessage)}</strong>
        <span>${escapeHtml(safeDetail)}</span>
      </p>
    `;
  }

  function runtimeValidationNotice(message) {
    const safeMessage = safeStr(message || "Panel content is advisory; commands still require runtime validation.");
    return `<p class="rpg-panel-runtime-notice" data-source="${escapeHtml(SOURCE)}" ${panelStateAttrs("advisory")} role="note" aria-label="Runtime validation notice">${escapeHtml(safeMessage)}</p>`;
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

  function decoratePanel(panelElement, panelId, source, state) {
    const attached = attachPanelToLayout(panelElement, panelId);
    if (!attached) return null;
    attached.setAttribute("data-panel-chrome-source", SOURCE);
    attached.setAttribute("data-panel-payload-source", safeStr(source || SOURCE));
    attached.setAttribute("data-panel-a11y-source", SOURCE);
    applyPanelState(attached, state || "ready");
    if (!attached.getAttribute("role")) attached.setAttribute("role", "region");
    if (!attached.getAttribute("aria-label")) attached.setAttribute("aria-label", panelChromeLabel(panelId));
    if (!attached.hasAttribute("tabindex")) attached.setAttribute("tabindex", "-1");
    return attached;
  }

  window.RpgPanelChrome = {
    SOURCE,
    PANEL_STATES,
    escapeHtml,
    panelChromeLabel,
    panelChromeA11yAttrs,
    panelChromeState,
    panelStateAttrs,
    applyPanelState,
    panelSourceBadge,
    panelEmptyState,
    runtimeValidationNotice,
    attachPanelToLayout,
    decoratePanel,
  };
})();