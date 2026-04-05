/**
 * Phase 8.4.6 — RPG Inspector UI
 *
 * Main controller that binds inspector actions to the UI.
 * Integrates with RPGPlayerIntegration to refresh timeline and audit data.
 */

import { RPGInspectorClient } from "./rpgInspectorClient.js";
import { rpgInspectorState } from "./rpgInspectorState.js";
import {
  renderInspectorShell,
  renderTimelinePanel,
  renderTickView,
  renderNpcReasoning,
  renderGmAudit,
} from "./rpgInspectorRenderer.js";

const inspectorClient = new RPGInspectorClient();

function getEl(id) {
  return document.getElementById(id);
}

export class RPGInspectorUI {
  constructor(getSetupPayload, getSimulationState) {
    this.getSetupPayload = getSetupPayload;
    this.getSimulationState = getSimulationState;
  }

  toggleOpen() {
    rpgInspectorState.isOpen = !rpgInspectorState.isOpen;
    renderInspectorShell(rpgInspectorState.isOpen);
  }

  async refreshTimeline() {
    try {
      const setupPayload = this.getSetupPayload();
      const res = await inspectorClient.getTimeline(setupPayload);
      rpgInspectorState.timeline = res.timeline;
      rpgInspectorState.latestDiff = res.latest_diff || {};
      renderTimelinePanel(
        res.timeline,
        res.latest_diff || {},
        async (tick) => {
          await this.selectTick(tick);
        }
      );
    } catch (e) {
      console.warn("Failed to refresh inspector timeline:", e);
    }
  }

  async selectTick(tick) {
    try {
      const setupPayload = this.getSetupPayload();
      const res = await inspectorClient.getTimelineTick(setupPayload, tick);
      rpgInspectorState.selectedTick = tick;
      rpgInspectorState.selectedTickView = res.tick_view;
      renderTickView(res.tick_view);
    } catch (e) {
      console.warn("Failed to select inspector tick:", e);
    }
  }

  async inspectNpc(npcId) {
    try {
      const setupPayload = this.getSetupPayload();
      const res = await inspectorClient.getNpcReasoning(setupPayload, npcId);
      rpgInspectorState.selectedNpcId = npcId;
      rpgInspectorState.npcReasoning = res.npc_reasoning;
      renderNpcReasoning(res.npc_reasoning);
    } catch (e) {
      console.warn("Failed to inspect NPC reasoning:", e);
    }
  }

  async forceNpcGoal() {
    const npcId = (getEl("rpg-inspector-npc-id")?.value || "").trim();
    const goalId = (getEl("rpg-inspector-goal-id")?.value || "").trim();
    const goalType = (getEl("rpg-inspector-goal-type")?.value || "").trim();
    const priority = parseFloat((getEl("rpg-inspector-goal-priority")?.value || "1").trim());
    if (!npcId) return;
    const setupPayload = this.getSetupPayload();
    try {
      await inspectorClient.forceNpcGoal(setupPayload, npcId, {
        goal_id: goalId || "gm_forced",
        type: goalType || "gm_override",
        priority: isNaN(priority) ? 1.0 : priority,
      });
      await this.refreshAudit();
      await this.inspectNpc(npcId);
    } catch (e) {
      console.warn("Failed to force NPC goal:", e);
    }
  }

  async forceFactionTrend() {
    const factionId = (getEl("rpg-inspector-faction-id")?.value || "").trim();
    const aggression = parseFloat((getEl("rpg-inspector-faction-aggression")?.value || "").trim());
    const momentum = parseFloat((getEl("rpg-inspector-faction-momentum")?.value || "").trim());
    if (!factionId) return;
    const setupPayload = this.getSetupPayload();
    const patch = {};
    if (!isNaN(aggression)) patch.aggression = aggression;
    if (!isNaN(momentum)) patch.momentum = momentum;
    try {
      await inspectorClient.forceFactionTrend(setupPayload, factionId, patch);
      await this.refreshAudit();
    } catch (e) {
      console.warn("Failed to force faction trend:", e);
    }
  }

  async addDebugNote() {
    const note = (getEl("rpg-inspector-debug-note")?.value || "").trim();
    if (!note) return;
    const setupPayload = this.getSetupPayload();
    try {
      await inspectorClient.addDebugNote(setupPayload, note);
      const input = getEl("rpg-inspector-debug-note");
      if (input) input.value = "";
      await this.refreshAudit();
    } catch (e) {
      console.warn("Failed to add debug note:", e);
    }
  }

  async refreshAudit() {
    const simulationState = this.getSimulationState();
    renderGmAudit((simulationState || {}).debug_meta || {});
  }

  bind() {
    // Auto-open once for developer visibility
    const savedOpen = localStorage.getItem("rpg_inspector_open");
    if (!rpgInspectorState.timeline || savedOpen === "1") {
      rpgInspectorState.isOpen = true;
      localStorage.setItem("rpg_inspector_open", "1");
      renderInspectorShell(true);
    }

    getEl("rpg-inspector-toggle-btn")?.addEventListener("click", () => {
      rpgInspectorState.isOpen = !rpgInspectorState.isOpen;
      localStorage.setItem("rpg_inspector_open", rpgInspectorState.isOpen ? "1" : "0");
      renderInspectorShell(rpgInspectorState.isOpen);
    });
    getEl("rpg-inspector-refresh-btn")?.addEventListener("click", async () => {
      await this.refreshTimeline();
      await this.refreshAudit();
    });
    getEl("rpg-inspector-inspect-npc-btn")?.addEventListener("click", async () => {
      const npcId = (getEl("rpg-inspector-npc-id")?.value || "").trim();
      if (npcId) await this.inspectNpc(npcId);
    });
    getEl("rpg-inspector-force-goal-btn")?.addEventListener("click", async () => {
      await this.forceNpcGoal();
    });
    getEl("rpg-inspector-force-faction-btn")?.addEventListener("click", async () => {
      await this.forceFactionTrend();
    });
    getEl("rpg-inspector-add-note-btn")?.addEventListener("click", async () => {
      await this.addDebugNote();
    });

    // Quick NPC inspect from timeline consequences
    window.addEventListener("rpg-inspector:inspectNpc", (e) => {
      if (e.detail) this.inspectNpc(e.detail);
    });
  }
}