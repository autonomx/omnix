(function () {
  "use strict";

  const STORAGE_KEY = "rpgConversationSettings";
  const SOURCE = "deterministic_conversation_settings";
  const DEFAULT_SETTINGS = {
    interactionPersistence: "until_next_command",
    backgroundSoftAudit: true,
    canUpdateState: false,
  };

  function safeJsonParse(value) {
    try {
      return JSON.parse(value);
    } catch (_error) {
      return null;
    }
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

  function chromeHelper() {
    return window.RpgPanelChrome || null;
  }

  function loadSettings() {
    const stored = safeJsonParse(window.localStorage.getItem(STORAGE_KEY) || "{}");
    return { ...DEFAULT_SETTINGS, ...(stored || {}) };
  }

  function saveSettings(settings) {
    const merged = { ...loadSettings(), ...(settings || {}) };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
    return merged;
  }

  function settingsSourceBadge() {
    const chrome = chromeHelper();
    if (chrome && typeof chrome.panelSourceBadge === "function") return chrome.panelSourceBadge(SOURCE, "local-settings");
    return `<span class="rpg-panel-source-badge">${escapeHtml(SOURCE)}</span>`;
  }

  function settingsRuntimeNotice() {
    const chrome = chromeHelper();
    if (chrome && typeof chrome.runtimeValidationNotice === "function") {
      return chrome.runtimeValidationNotice("Conversation settings only affect presentation/audit preferences; gameplay state changes still go through runtime validation.");
    }
    return '<p class="rpg-conversation-settings-notice">Conversation settings only affect presentation/audit preferences; gameplay state changes still go through runtime validation.</p>';
  }

  function ensurePanel() {
    let panel = document.getElementById("rpgConversationSettingsPanel");
    if (panel) return panel;

    const host =
      document.getElementById("rpg-top-panels") ||
      document.querySelector(".rpg-top-panels") ||
      document.getElementById("rpgView") ||
      document.body;

    panel = document.createElement("section");
    panel.id = "rpgConversationSettingsPanel";
    panel.className = "rpg-conversation-settings-panel";
    panel.innerHTML = `
      <div class="rpg-panel-header" data-panel-chrome="deterministic_phase8_panel_chrome">
        <span>Conversation settings</span>
        ${settingsSourceBadge()}
      </div>
      ${settingsRuntimeNotice()}
      <div class="rpg-panel-content">
        <label class="rpg-setting-row">
          <span>Interaction memory</span>
          <select id="rpgInteractionPersistenceSelect">
            <option value="single_turn">Single turn</option>
            <option value="until_next_command">Until next command</option>
            <option value="session">Session</option>
          </select>
        </label>
        <label class="rpg-setting-row">
          <input type="checkbox" id="rpgBackgroundSoftAuditToggle" />
          <span>Background grounding audit</span>
        </label>
        <label class="rpg-setting-row">
          <input type="checkbox" id="rpgCanUpdateStateToggle" />
          <span>Allow audit state updates</span>
        </label>
        <div class="rpg-conversation-settings-source">Source: ${escapeHtml(SOURCE)}</div>
      </div>
    `;
    const chrome = chromeHelper();
    if (chrome && typeof chrome.decoratePanel === "function") {
      chrome.decoratePanel(panel, "conversation-settings", SOURCE);
    } else {
      host.appendChild(panel);
    }
    return panel;
  }

  function render() {
    const panel = ensurePanel();
    const settings = loadSettings();
    const chrome = chromeHelper();
    const persistence = panel.querySelector("#rpgInteractionPersistenceSelect");
    const audit = panel.querySelector("#rpgBackgroundSoftAuditToggle");
    const updateState = panel.querySelector("#rpgCanUpdateStateToggle");

    if (chrome && typeof chrome.decoratePanel === "function") {
      chrome.decoratePanel(panel, "conversation-settings", SOURCE);
    }
    panel.dataset.source = SOURCE;
    panel.dataset.panelChrome = "deterministic_phase8_panel_chrome";

    if (persistence) persistence.value = settings.interactionPersistence || DEFAULT_SETTINGS.interactionPersistence;
    if (audit) audit.checked = settings.backgroundSoftAudit !== false;
    if (updateState) updateState.checked = settings.canUpdateState === true;

    if (persistence && !persistence.dataset.bound) {
      persistence.dataset.bound = "true";
      persistence.addEventListener("change", () => {
        saveSettings({ interactionPersistence: persistence.value });
      });
    }
    if (audit && !audit.dataset.bound) {
      audit.dataset.bound = "true";
      audit.addEventListener("change", () => {
        saveSettings({ backgroundSoftAudit: audit.checked });
      });
    }
    if (updateState && !updateState.dataset.bound) {
      updateState.dataset.bound = "true";
      updateState.addEventListener("change", () => {
        saveSettings({ canUpdateState: updateState.checked });
      });
    }

    return panel;
  }

  function attachToPayload(payload) {
    const settings = loadSettings();
    if (!payload || typeof payload !== "object") return { settings };
    payload.conversation_settings = settings;
    return payload;
  }

  function appendDeferredScript(id, src) {
    if (document.getElementById(id)) return;
    const script = document.createElement("script");
    script.id = id;
    script.src = src;
    script.defer = true;
    document.head.appendChild(script);
  }

  function appendStylesheet(id, href) {
    if (document.getElementById(id)) return;
    const link = document.createElement("link");
    link.id = id;
    link.rel = "stylesheet";
    link.href = href;
    document.head.appendChild(link);
  }

  function ensurePlayerFocusAssets() {
    appendStylesheet("rpg-player-focus-css", "/static/rpg/rpg-player-focus.css");
    if (!window.RpgPlayerFocus && !document.getElementById("rpg-player-focus-script")) {
      appendDeferredScript("rpg-player-focus-script", "/static/rpg/rpg-player-focus.js");
    }
  }

  function ensureCommandBridgeScript() {
    if (window.RpgCommandBridge || document.getElementById("rpg-command-bridge-script")) return;
    appendDeferredScript("rpg-command-bridge-script", "/static/rpg/rpg-command-bridge.js");
  }

  function ensureLivePayloadBridgeScript() {
    if (window.RpgLivePayloadBridge || document.getElementById("rpg-live-payload-bridge-script")) return;
    appendDeferredScript("rpg-live-payload-bridge-script", "/static/rpg/rpg-live-payload-bridge.js");
  }

  function ensurePanelLayoutRegistryScript() {
    if (window.RpgPanelLayoutRegistry || document.getElementById("rpg-panel-layout-registry-script")) return;
    appendDeferredScript("rpg-panel-layout-registry-script", "/static/rpg/rpgPanelLayoutRegistry.js");
  }

  function ensurePanelChromeScript() {
    if (window.RpgPanelChrome || document.getElementById("rpg-panel-chrome-script")) return;
    appendDeferredScript("rpg-panel-chrome-script", "/static/rpg/rpgPanelChrome.js");
  }

  function ensureMapLocationPanelScript() {
    if (window.RpgMapLocationPanel || document.getElementById("rpg-map-location-panel-script")) return;
    appendDeferredScript("rpg-map-location-panel-script", "/static/rpg/rpgMapLocationPanel.js");
  }

  function ensurePlayerHudScript() {
    if (window.RpgPlayerHud || document.getElementById("rpg-player-hud-script")) return;
    appendDeferredScript("rpg-player-hud-script", "/static/rpg/rpgPlayerHud.js");
  }

  function ensureObjectiveJournalPanelScript() {
    if (window.RpgObjectiveJournalPanel || document.getElementById("rpg-objective-journal-panel-script")) return;
    appendDeferredScript("rpg-objective-journal-panel-script", "/static/rpg/rpgObjectiveJournalPanel.js");
  }

  function ensureCombatActionPanelScript() {
    if (window.RpgCombatActionPanel || document.getElementById("rpg-combat-action-panel-script")) return;
    appendDeferredScript("rpg-combat-action-panel-script", "/static/rpg/rpgCombatActionPanel.js");
  }

  function ensureInventoryPartyPanelScript() {
    if (window.RpgInventoryPartyPanel || document.getElementById("rpg-inventory-party-panel-script")) return;
    appendDeferredScript("rpg-inventory-party-panel-script", "/static/rpg/rpgInventoryPartyPanel.js");
  }

  function ensureRecentActivityPanelScript() {
    if (window.RpgRecentActivityPanel || document.getElementById("rpg-recent-activity-panel-script")) return;
    appendDeferredScript("rpg-recent-activity-panel-script", "/static/rpg/rpgRecentActivityPanel.js");
  }

  function ensureSuggestedActionsPanelScript() {
    if (window.RpgSuggestedActionsPanel || document.getElementById("rpg-suggested-actions-panel-script")) return;
    appendDeferredScript("rpg-suggested-actions-panel-script", "/static/rpg/rpgSuggestedActionsPanel.js");
  }

  function ensureNextActionButtonsScript() {
    if (window.RpgNextActionButtons || document.getElementById("rpg-next-action-buttons-script")) return;
    appendDeferredScript("rpg-next-action-buttons-script", "/static/rpg/rpgNextActionButtons.js");
  }

  function ensureSurvivalInspectorScript() {
    if (window.RpgSurvivalInspector || document.getElementById("rpg-survival-inspector-script")) return;
    ensureCommandBridgeScript();
    ensureLivePayloadBridgeScript();
    ensurePanelLayoutRegistryScript();
    ensurePanelChromeScript();
    ensureMapLocationPanelScript();
    ensurePlayerHudScript();
    ensureObjectiveJournalPanelScript();
    ensureCombatActionPanelScript();
    ensureInventoryPartyPanelScript();
    ensureRecentActivityPanelScript();
    ensureSuggestedActionsPanelScript();
    ensureNextActionButtonsScript();
    appendDeferredScript("rpg-survival-inspector-script", "/static/rpg/rpg-survival-inspector.js");
  }

  window.RpgConversationSettings = {
    render,
    loadSettings,
    saveSettings,
    attachToPayload,
    ensurePlayerFocusAssets,
    ensureCommandBridgeScript,
    ensureLivePayloadBridgeScript,
    ensurePanelLayoutRegistryScript,
    ensurePanelChromeScript,
    ensureMapLocationPanelScript,
    ensurePlayerHudScript,
    ensureObjectiveJournalPanelScript,
    ensureCombatActionPanelScript,
    ensureInventoryPartyPanelScript,
    ensureRecentActivityPanelScript,
    ensureSuggestedActionsPanelScript,
    ensureNextActionButtonsScript,
    ensureSurvivalInspectorScript,
  };

  function initConversationSettings() {
    ensurePlayerFocusAssets();
    ensureCommandBridgeScript();
    ensureLivePayloadBridgeScript();
    ensurePanelLayoutRegistryScript();
    ensurePanelChromeScript();
    render();
    ensureMapLocationPanelScript();
    ensurePlayerHudScript();
    ensureObjectiveJournalPanelScript();
    ensureCombatActionPanelScript();
    ensureInventoryPartyPanelScript();
    ensureRecentActivityPanelScript();
    ensureSuggestedActionsPanelScript();
    ensureNextActionButtonsScript();
    ensureSurvivalInspectorScript();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initConversationSettings);
  } else {
    initConversationSettings();
  }
})();
