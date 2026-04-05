/**
 * Phase 8.4.6 — RPG Inspector State
 *
 * Shared state object for the RPG inspector panels.
 */

export const rpgInspectorState = {
  timeline: null,
  latestDiff: null,
  selectedTick: null,
  selectedTickView: null,
  selectedNpcId: "",
  npcReasoning: null,
  isOpen: false,
};

export function resetInspectorState() {
  rpgInspectorState.timeline = null;
  rpgInspectorState.latestDiff = null;
  rpgInspectorState.selectedTick = null;
  rpgInspectorState.selectedTickView = null;
  rpgInspectorState.selectedNpcId = "";
  rpgInspectorState.npcReasoning = null;
}