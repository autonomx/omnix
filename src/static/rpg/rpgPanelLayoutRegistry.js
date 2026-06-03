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

  function ensurePanelRoot() {
    let root = document.getElementById("rpg-top-panels");
    if (!root) {
      root = document.createElement("section");
      root.id = "rpg-top-panels";
      root.className = "rpg-top-panels";
      document.body.appendChild(root);
    }
    root.setAttribute("data-panel-layout-source", SOURCE);
    return root;
  }

  function ensurePanelSlot(panelId) {
    const root = ensurePanelRoot();
    let slot = document.getElementById(`rpg-panel-slot-${panelId}`);
    if (!slot) {
      slot = document.createElement("section");
      slot.id = `rpg-panel-slot-${panelId}`;
      slot.className = "rpg-panel-slot";
      slot.setAttribute("data-panel-id", panelId);
      slot.setAttribute("data-source", SOURCE);
      root.appendChild(slot);
    }
    return slot;
  }

  function ensureOrderedPanelSlots() {
    PANEL_ORDER.forEach(ensurePanelSlot);
    return ensurePanelRoot();
  }

  function attachPanelToSlot(panelElement, panelId) {
    const slot = ensurePanelSlot(panelId);
    if (!panelElement || !slot) return null;
    if (panelElement.parentElement !== slot) slot.appendChild(panelElement);
    panelElement.setAttribute("data-layout-slot", panelId);
    panelElement.setAttribute("data-layout-source", SOURCE);
    return panelElement;
  }

  function panelOrder() {
    return PANEL_ORDER.slice();
  }

  window.RpgPanelLayoutRegistry = {
    SOURCE,
    panelOrder,
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
