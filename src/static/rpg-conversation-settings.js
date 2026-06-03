(function () {
  "use strict";

  const STORAGE_KEY = "rpgConversationSettings";
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

  function loadSettings() {
    const stored = safeJsonParse(window.localStorage.getItem(STORAGE_KEY) || "{}");
    return { ...DEFAULT_SETTINGS, ...(stored || {}) };
  }

  function saveSettings(settings) {
    const merged = { ...loadSettings(), ...(settings || {}) };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
    return merged;
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
      <div class="rpg-panel-header">
        <span>Conversation settings</span>
      </div>
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
      </div>
    `;
    const chrome = window.RpgPanelChrome;
    if (chrome && typeof chrome.decoratePanel === "function") {
      chrome.decoratePanel(panel, "conversation-settings", "deterministic_conversation_settings");
    } else {
      host.appendChild(panel);
    }
    return panel;
  }

  function render() {
    const panel = ensurePanel();
    const settings = loadSettings();
    const persistence = panel.querySelector("#rpgInteractionPersistenceSelect");
    const audit = panel.querySelector("#rpgBackgroundSoftAuditToggle");
    const updateState = panel.querySelector("#rpgCanUpdateStateToggle");

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
    appendDeferredScript("rpg-survival-inspector-script", "/static/rpg/rpg-survival-inspector.js");
  }

  window.RpgConversationSettings = {
    render,
    loadSettings,
    saveSettings,
    attachToPayload,
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
    ensureSurvivalInspectorScript,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
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
      ensureSurvivalInspectorScript();
    });
  } else {
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
    ensureSurvivalInspectorScript();
  }
})();
