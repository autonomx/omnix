(function () {
  "use strict";

  const SOURCE = "deterministic_phase8_panel_chrome";
  const READ_ONLY_AUTHORITY = "runtime_validated_commands_only";
  const FOCUS_TARGET = "panel_region";
  const PANEL_DENSITIES = {
    compact: "compact",
    normal: "normal",
  };
  const PANEL_FRESHNESS = {
    live: "live",
    missing: "missing",
    snapshot: "snapshot",
    stale: "stale",
  };
  const PANEL_PRIORITIES = {
    critical: "critical",
    high: "high",
    low: "low",
    normal: "normal",
  };
  const PANEL_PROVENANCE = {
    chrome: "chrome",
    layout_registry: "layout_registry",
    payload: "payload",
    runtime_contract: "runtime_contract",
  };
  const PANEL_RENDER_KINDS = {
    badge: "badge",
    empty_state: "empty_state",
    notice: "notice",
    panel: "panel",
  };
  const PANEL_SECTIONS = {
    body: "body",
    footer: "footer",
    header: "header",
    root: "root",
  };
  const PANEL_STATES = {
    advisory: "advisory",
    empty: "empty",
    ready: "ready",
    source_backed: "source_backed",
  };
  const PANEL_TONES = {
    info: "info",
    muted: "muted",
    neutral: "neutral",
    warning: "warning",
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

  function safeToken(value, fallback) {
    return safeStr(value || fallback).toLowerCase().replace(/-/g, "_");
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

  function panelChromeDensity(density) {
    const safeDensity = safeToken(density, PANEL_DENSITIES.normal);
    return Object.prototype.hasOwnProperty.call(PANEL_DENSITIES, safeDensity) ? PANEL_DENSITIES[safeDensity] : PANEL_DENSITIES.normal;
  }

  function densityAttrs(density) {
    const safeDensity = panelChromeDensity(density);
    return `data-panel-density="${escapeHtml(safeDensity)}" data-panel-density-source="${escapeHtml(SOURCE)}"`;
  }

  function panelChromeFreshness(freshness) {
    const safeFreshness = safeToken(freshness, PANEL_FRESHNESS.live);
    return Object.prototype.hasOwnProperty.call(PANEL_FRESHNESS, safeFreshness) ? PANEL_FRESHNESS[safeFreshness] : PANEL_FRESHNESS.live;
  }

  function freshnessAttrs(freshness) {
    const safeFreshness = panelChromeFreshness(freshness);
    return `data-panel-freshness="${escapeHtml(safeFreshness)}" data-panel-freshness-source="${escapeHtml(SOURCE)}"`;
  }

  function panelChromePriority(priority) {
    const safePriority = safeToken(priority, PANEL_PRIORITIES.normal);
    return Object.prototype.hasOwnProperty.call(PANEL_PRIORITIES, safePriority) ? PANEL_PRIORITIES[safePriority] : PANEL_PRIORITIES.normal;
  }

  function priorityAttrs(priority) {
    const safePriority = panelChromePriority(priority);
    return `data-panel-priority="${escapeHtml(safePriority)}" data-panel-priority-source="${escapeHtml(SOURCE)}"`;
  }

  function panelChromeProvenance(provenance) {
    const safeProvenance = safeToken(provenance, PANEL_PROVENANCE.chrome);
    return Object.prototype.hasOwnProperty.call(PANEL_PROVENANCE, safeProvenance) ? PANEL_PROVENANCE[safeProvenance] : PANEL_PROVENANCE.chrome;
  }

  function provenanceAttrs(provenance) {
    const safeProvenance = panelChromeProvenance(provenance);
    return `data-panel-provenance="${escapeHtml(safeProvenance)}" data-panel-provenance-source="${escapeHtml(SOURCE)}"`;
  }

  function panelChromeRenderKind(renderKind) {
    const safeRenderKind = safeToken(renderKind, PANEL_RENDER_KINDS.panel);
    return Object.prototype.hasOwnProperty.call(PANEL_RENDER_KINDS, safeRenderKind) ? PANEL_RENDER_KINDS[safeRenderKind] : PANEL_RENDER_KINDS.panel;
  }

  function renderKindAttrs(renderKind) {
    const safeRenderKind = panelChromeRenderKind(renderKind);
    return `data-panel-render-kind="${escapeHtml(safeRenderKind)}" data-panel-render-source="${escapeHtml(SOURCE)}"`;
  }

  function panelChromeSection(section) {
    const safeSection = safeToken(section, PANEL_SECTIONS.body);
    return Object.prototype.hasOwnProperty.call(PANEL_SECTIONS, safeSection) ? PANEL_SECTIONS[safeSection] : PANEL_SECTIONS.body;
  }

  function sectionAttrs(section) {
    const safeSection = panelChromeSection(section);
    return `data-panel-section="${escapeHtml(safeSection)}" data-panel-section-source="${escapeHtml(SOURCE)}"`;
  }

  function panelChromeState(state) {
    const safeState = safeToken(state, PANEL_STATES.source_backed);
    return Object.prototype.hasOwnProperty.call(PANEL_STATES, safeState) ? PANEL_STATES[safeState] : PANEL_STATES.source_backed;
  }

  function panelStateAttrs(state) {
    const safeState = panelChromeState(state);
    return `data-panel-state="${escapeHtml(safeState)}" data-panel-state-source="${escapeHtml(SOURCE)}"`;
  }

  function panelChromeTone(tone) {
    const safeTone = safeToken(tone, PANEL_TONES.neutral);
    return Object.prototype.hasOwnProperty.call(PANEL_TONES, safeTone) ? PANEL_TONES[safeTone] : PANEL_TONES.neutral;
  }

  function toneAttrs(tone) {
    const safeTone = panelChromeTone(tone);
    return `data-panel-tone="${escapeHtml(safeTone)}" data-panel-tone-source="${escapeHtml(SOURCE)}"`;
  }

  function readOnlyAttrs(reason) {
    const safeReason = safeStr(reason || "Panel is presentation-only; gameplay authority stays with runtime validation.");
    return `data-panel-read-only="true" data-panel-authority="${escapeHtml(READ_ONLY_AUTHORITY)}" data-panel-read-only-source="${escapeHtml(SOURCE)}" aria-readonly="true" data-panel-read-only-reason="${escapeHtml(safeReason)}"`;
  }

  function focusAttrs(focusLabel) {
    const safeLabel = safeStr(focusLabel || "Panel region focus target");
    return `data-panel-focus-target="${escapeHtml(FOCUS_TARGET)}" data-panel-focus-source="${escapeHtml(SOURCE)}" data-panel-focus-label="${escapeHtml(safeLabel)}" tabindex="-1"`;
  }

  function applyFocusMetadata(panelElement, focusLabel) {
    if (!panelElement) return null;
    const safeLabel = safeStr(focusLabel || "Panel region focus target");
    panelElement.setAttribute("data-panel-focus-target", FOCUS_TARGET);
    panelElement.setAttribute("data-panel-focus-source", SOURCE);
    panelElement.setAttribute("data-panel-focus-label", safeLabel);
    if (!panelElement.hasAttribute("tabindex")) panelElement.setAttribute("tabindex", "-1");
    return panelElement;
  }

  function applyReadOnlyMetadata(panelElement, reason) {
    if (!panelElement) return null;
    const safeReason = safeStr(reason || "Panel is presentation-only; gameplay authority stays with runtime validation.");
    panelElement.setAttribute("data-panel-read-only", "true");
    panelElement.setAttribute("data-panel-authority", READ_ONLY_AUTHORITY);
    panelElement.setAttribute("data-panel-read-only-source", SOURCE);
    panelElement.setAttribute("aria-readonly", "true");
    panelElement.setAttribute("data-panel-read-only-reason", safeReason);
    return panelElement;
  }

  function applyDensityMetadata(panelElement, density) {
    if (!panelElement) return null;
    const safeDensity = panelChromeDensity(density);
    panelElement.setAttribute("data-panel-density", safeDensity);
    panelElement.setAttribute("data-panel-density-source", SOURCE);
    return panelElement;
  }

  function applyFreshnessMetadata(panelElement, freshness) {
    if (!panelElement) return null;
    const safeFreshness = panelChromeFreshness(freshness);
    panelElement.setAttribute("data-panel-freshness", safeFreshness);
    panelElement.setAttribute("data-panel-freshness-source", SOURCE);
    return panelElement;
  }

  function applyPriorityMetadata(panelElement, priority) {
    if (!panelElement) return null;
    const safePriority = panelChromePriority(priority);
    panelElement.setAttribute("data-panel-priority", safePriority);
    panelElement.setAttribute("data-panel-priority-source", SOURCE);
    return panelElement;
  }

  function applyProvenanceMetadata(panelElement, provenance) {
    if (!panelElement) return null;
    const safeProvenance = panelChromeProvenance(provenance);
    panelElement.setAttribute("data-panel-provenance", safeProvenance);
    panelElement.setAttribute("data-panel-provenance-source", SOURCE);
    return panelElement;
  }

  function applyRenderKindMetadata(panelElement, renderKind) {
    if (!panelElement) return null;
    const safeRenderKind = panelChromeRenderKind(renderKind);
    panelElement.setAttribute("data-panel-render-kind", safeRenderKind);
    panelElement.setAttribute("data-panel-render-source", SOURCE);
    return panelElement;
  }

  function applySectionMetadata(sectionElement, section) {
    if (!sectionElement) return null;
    const safeSection = panelChromeSection(section);
    sectionElement.setAttribute("data-panel-section", safeSection);
    sectionElement.setAttribute("data-panel-section-source", SOURCE);
    return sectionElement;
  }

  function applyPanelState(panelElement, state) {
    if (!panelElement) return null;
    const safeState = panelChromeState(state);
    panelElement.setAttribute("data-panel-state", safeState);
    panelElement.setAttribute("data-panel-state-source", SOURCE);
    return panelElement;
  }

  function applyToneMetadata(panelElement, tone) {
    if (!panelElement) return null;
    const safeTone = panelChromeTone(tone);
    panelElement.setAttribute("data-panel-tone", safeTone);
    panelElement.setAttribute("data-panel-tone-source", SOURCE);
    return panelElement;
  }

  function panelSourceBadge(source, label, freshness, priority) {
    const safeSource = safeStr(source || SOURCE);
    const safeLabel = safeStr(label || "source-backed");
    return `<span class="rpg-panel-source-badge" data-source="${escapeHtml(safeSource)}" ${panelStateAttrs("source_backed")} ${sectionAttrs("header")} ${freshnessAttrs(freshness || "live")} ${priorityAttrs(priority || "normal")} ${provenanceAttrs("payload")} ${toneAttrs("info")} ${renderKindAttrs("badge")} role="note" aria-label="Panel source: ${escapeHtml(safeLabel)}">${escapeHtml(safeLabel)}</span>`;
  }

  function panelEmptyState(message, detail) {
    const safeMessage = safeStr(message || "No source-backed entries are currently visible.");
    const safeDetail = safeStr(detail || "This panel is read-only and will update when deterministic runtime payloads include data.");
    return `
      <p class="rpg-panel-empty-state" data-source="${escapeHtml(SOURCE)}" ${panelStateAttrs("empty")} ${sectionAttrs("body")} ${freshnessAttrs("missing")} ${priorityAttrs("low")} ${provenanceAttrs("chrome")} ${toneAttrs("muted")} ${renderKindAttrs("empty_state")} ${readOnlyAttrs("Empty panel content is presentation-only and source-backed.")} role="status" aria-live="polite">
        <strong>${escapeHtml(safeMessage)}</strong>
        <span>${escapeHtml(safeDetail)}</span>
      </p>
    `;
  }

  function runtimeValidationNotice(message) {
    const safeMessage = safeStr(message || "Panel content is advisory; commands still require runtime validation.");
    return `<p class="rpg-panel-runtime-notice" data-source="${escapeHtml(SOURCE)}" ${panelStateAttrs("advisory")} ${sectionAttrs("footer")} ${freshnessAttrs("live")} ${priorityAttrs("high")} ${provenanceAttrs("runtime_contract")} ${toneAttrs("warning")} ${renderKindAttrs("notice")} ${readOnlyAttrs("Runtime validation remains authoritative for gameplay commands.")} role="note" aria-label="Runtime validation notice">${escapeHtml(safeMessage)}</p>`;
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

  function decoratePanel(panelElement, panelId, source, state, freshness, priority, renderKind, provenance, tone) {
    const attached = attachPanelToLayout(panelElement, panelId);
    if (!attached) return null;
    attached.setAttribute("data-panel-chrome-source", SOURCE);
    attached.setAttribute("data-panel-payload-source", safeStr(source || SOURCE));
    attached.setAttribute("data-panel-a11y-source", SOURCE);
    applyPanelState(attached, state || "ready");
    applyReadOnlyMetadata(attached);
    applyDensityMetadata(attached, "normal");
    applyFreshnessMetadata(attached, freshness || "live");
    applyPriorityMetadata(attached, priority || "normal");
    applyProvenanceMetadata(attached, provenance || "chrome");
    applyToneMetadata(attached, tone || "neutral");
    applyRenderKindMetadata(attached, renderKind || "panel");
    applySectionMetadata(attached, "root");
    applyFocusMetadata(attached, panelChromeLabel(panelId));
    if (!attached.getAttribute("role")) attached.setAttribute("role", "region");
    if (!attached.getAttribute("aria-label")) attached.setAttribute("aria-label", panelChromeLabel(panelId));
    return attached;
  }

  window.RpgPanelChrome = {
    SOURCE,
    READ_ONLY_AUTHORITY,
    FOCUS_TARGET,
    PANEL_DENSITIES,
    PANEL_FRESHNESS,
    PANEL_PRIORITIES,
    PANEL_PROVENANCE,
    PANEL_RENDER_KINDS,
    PANEL_SECTIONS,
    PANEL_STATES,
    PANEL_TONES,
    escapeHtml,
    panelChromeLabel,
    panelChromeA11yAttrs,
    panelChromeDensity,
    densityAttrs,
    panelChromeFreshness,
    freshnessAttrs,
    panelChromePriority,
    priorityAttrs,
    panelChromeProvenance,
    provenanceAttrs,
    panelChromeRenderKind,
    renderKindAttrs,
    panelChromeSection,
    sectionAttrs,
    panelChromeState,
    panelStateAttrs,
    panelChromeTone,
    toneAttrs,
    readOnlyAttrs,
    focusAttrs,
    applyFocusMetadata,
    applyReadOnlyMetadata,
    applyDensityMetadata,
    applyFreshnessMetadata,
    applyPriorityMetadata,
    applyProvenanceMetadata,
    applyRenderKindMetadata,
    applySectionMetadata,
    applyPanelState,
    applyToneMetadata,
    panelSourceBadge,
    panelEmptyState,
    runtimeValidationNotice,
    attachPanelToLayout,
    decoratePanel,
  };
})();