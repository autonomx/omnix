(function () {
  "use strict";

  const SOURCE = "deterministic_phase8_panel_layout_registry";
  const PANEL_ORDER = [
    "conversation-settings",
    "map-location",
    "player-hud",
    "objective-journal",
    "combat-action",
    "inventory-party",
    "recent-activity",
    "suggested-actions",
    "survival-inspector",
  ];
  const PANEL_LABELS = {
    "conversation-settings": "Conversation settings panel",
    "map-location": "Map and location panel",
    "player-hud": "Player HUD panel",
    "objective-journal": "Objective journal panel",
    "combat-action": "Combat action panel",
    "inventory-party": "Inventory and party panel",
    "recent-activity": "Recent activity panel",
    "suggested-actions": "Suggested actions panel",
    "survival-inspector": "Survival inspector panel",
  };

  function safePanelId(panelId) {
    panelId = String(panelId || "");
    return PANEL_ORDER.indexOf(panelId) >= 0 ? panelId : "unknown-panel";
  }

  function panelLabel(panelId) {
    panelId = safePanelId(panelId);
    return PANEL_LABELS[panelId] || "RPG panel";
  }

  function panelIndex(panelId) {
    const idx = PANEL_ORDER.indexOf(panelId);
    return idx >= 0 ? idx + 1 : PANEL_ORDER.length + 1;
  }

  function ensurePanelRoot() {
    let root = document.getElementById("rpg-top-panels");
    if (!root) {
      root = document.createElement("section");
      root.id = "rpg-top-panels";
      root.className = "rpg-top-panels";
      document.body.appendChild(root);
    }
    root.setAttribute("data-panel-layout-source", SOURCE);
    root.setAttribute("role", "region");
    root.setAttribute("aria-label", "RPG status panels");
    return root;
  }

  function ensurePanelSlot(panelId) {
    panelId = safePanelId(panelId);
    const root = ensurePanelRoot();
    let slot = document.getElementById(`rpg-panel-slot-${panelId}`);
    if (!slot) {
      slot = document.createElement("section");
      slot.id = `rpg-panel-slot-${panelId}`;
      slot.className = "rpg-panel-slot";
      root.appendChild(slot);
    }
    slot.setAttribute("data-panel-id", panelId);
    slot.setAttribute("data-source", SOURCE);
    slot.setAttribute("data-panel-order", String(panelIndex(panelId)));
    slot.setAttribute("role", "region");
    slot.setAttribute("aria-label", panelLabel(panelId));
    return slot;
  }

  function ensureOrderedPanelSlots() {
    PANEL_ORDER.forEach(ensurePanelSlot);
    return ensurePanelRoot();
  }

  function attachPanelToSlot(panelElement, panelId) {
    panelId = safePanelId(panelId);
    const slot = ensurePanelSlot(panelId);
    if (!panelElement || !slot) return null;
    if (panelElement.parentElement !== slot) slot.appendChild(panelElement);
    panelElement.setAttribute("data-layout-slot", panelId);
    panelElement.setAttribute("data-layout-source", SOURCE);
    panelElement.setAttribute("data-panel-order", String(panelIndex(panelId)));
    panelElement.setAttribute("aria-label", panelLabel(panelId));
    return panelElement;
  }

  function panelOrder() {
    return PANEL_ORDER.slice();
  }

  function panelLabels() {
    return Object.assign({}, PANEL_LABELS);
  }

  window.RpgPanelLayoutRegistry = {
    SOURCE,
    panelOrder,
    panelLabels,
    panelLabel,
    panelIndex,
    ensurePanelRoot,
    ensurePanelSlot,
    ensureOrderedPanelSlots,
    attachPanelToSlot,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ensureOrderedPanelSlots);
  } else {
    ensureOrderedPanelSlots();
  }
})();