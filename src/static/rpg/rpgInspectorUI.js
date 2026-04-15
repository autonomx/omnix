/**
 * Phase 8.4.6 — RPG Inspector UI
 *
 * Main controller that binds inspector actions to the UI.
 * Integrates with RPGPlayerIntegration to refresh timeline and audit data.
 */



const inspectorClient = new RPGInspectorClient();

function getEl(id) {
  return document.getElementById(id);
}

function nowIso() {
  return new Date().toISOString();
}

function safeObj(v) {
  return v && typeof v === "object" ? v : {};
}

function pushBoundedEvent(target, entry, maxItems = 24) {
  const list = Array.isArray(target) ? target.slice() : [];
  list.push(entry);
  return list.slice(-maxItems);
}

// Auto-initialize inspector when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
  console.log("DOM Ready - initializing RPG Inspector");
  
  // Wait for RPG module to initialize first
  setTimeout(() => {
    console.log("Creating RPGInspectorUI instance");
    
    // Create empty stubs for required getters
    window.rpgInspector = new RPGInspectorUI(
      () => window.rpgState ? { session_id: window.rpgState.sessionId } : {},
      () => window.rpgState || {}
    );
    
    // Expose globally
    window.RPGInspectorUI = RPGInspectorUI;
    
    console.log("Calling bind()");
    window.rpgInspector.bind();
    
    // Force initial render to create the panel
    const shell = document.getElementById("rpg-inspector-shell");
    if (shell) {
      console.log("Found inspector shell");
      shell.style.display = "none";
    } else {
      console.error("Inspector shell NOT found!");
    }
    
    // Add direct click handler to button
    const btn = document.getElementById("rpg-inspector-toggle-btn");
    if (btn) {
      console.log("Found inspector toggle button, adding listener");
      btn.addEventListener("click", () => {
        console.log("Inspector button clicked!");
        if (!window.rpgInspector) {
          console.error("rpgInspector not initialized!");
          return;
        }
        console.log("Toggling inspector open state");
        window.rpgInspector.toggleOpen();
      });
    } else {
      console.error("Inspector toggle button NOT found!");
    }
  }, 1000);
});

class RPGInspectorUI {
  constructor(getSetupPayload, getSimulationState) {
    this.getSetupPayload = getSetupPayload;
    this.getSimulationState = getSimulationState;
    this._sseDiagBound = false;
  }

  handleSseDiagnostic(detail) {
    const d = safeObj(detail);
    const channel = String(d.channel || "");
    if (!channel || !rpgInspectorState.sseDiagnostics[channel]) return;

    const prev = safeObj(rpgInspectorState.sseDiagnostics[channel]);
    const meta = safeObj(d.meta);

    const next = {
      ...prev,
      ...safeObj(d.patch),
      events: pushBoundedEvent(prev.events, {
        at: d.at || nowIso(),
        channel,
        kind: d.kind || "event",
        meta,
      }),
    };

    rpgInspectorState.sseDiagnostics[channel] = next;
    renderSseDiagnosticsPanel(rpgInspectorState.sseDiagnostics);
  }

  toggleOpen() {
    rpgInspectorState.isOpen = !rpgInspectorState.isOpen;
    localStorage.setItem("rpg_inspector_open", rpgInspectorState.isOpen ? "1" : "0");
    renderInspectorShell(rpgInspectorState.isOpen);
  }

  async refreshTimeline() {
    setInspectorLoading(true);
    try {
      const setupPayload = this.getSetupPayload();
      const res = await inspectorClient.getTimeline(setupPayload);
      rpgInspectorState.timeline = res.timeline;
      rpgInspectorState.latestDiff = res.latest_diff || {};
      const filteredTimeline = {
        ...res.timeline,
        snapshots: filterTimelineSnapshots((res.timeline || {}).snapshots || [], rpgInspectorState.timelineQuery),
        recent_world_consequences: filterWorldConsequences(
          (res.timeline || {}).recent_world_consequences || [],
          rpgInspectorState.worldConsequenceFilter
        ),
      };
      renderTimelinePanel(
        filteredTimeline,
        res.latest_diff || {},
        async (tick) => {
          await this.selectTick(tick);
        }
      );
      // Phase 8.4.7 fix — event delegation for consequence inspect buttons
      const timelineEl = document.getElementById("rpg-inspector-timeline");
      if (timelineEl && !timelineEl._consequenceDelegationBound) {
        timelineEl._consequenceDelegationBound = true;
        timelineEl.addEventListener("click", async (e) => {
          const btn = e.target.closest("[data-consequence-type]");
          if (!btn) return;
          const type = btn.getAttribute("data-consequence-type") || "all";
          rpgInspectorState.worldConsequenceFilter = type;
          const filterEl = document.getElementById("rpg-inspector-world-filter");
          if (filterEl) filterEl.value = type;
          await this.refreshTimeline();
        });
      }
      renderInspectorDiff(res.latest_diff || {});
      rpgInspectorState.causalTrace = buildCausalTrace({
        latestDiff: res.latest_diff || {},
        timeline: res.timeline || {},
        npcReasoning: rpgInspectorState.npcReasoning || {},
      });
      renderCausalTrace(rpgInspectorState.causalTrace);
      this.populateNpcOptions();
    } catch (e) {
      console.warn("Failed to refresh inspector timeline:", e);
    } finally {
      setInspectorLoading(false);
    }
  }

  async selectTick(tick) {
    setInspectorLoading(true);
    try {
      const setupPayload = this.getSetupPayload();
      const res = await inspectorClient.getTimelineTick(setupPayload, tick);
      rpgInspectorState.selectedTick = tick;
      rpgInspectorState.selectedTickView = res.tick_view;
      renderTickView(res.tick_view);
      await this.refreshTimeline();
    } catch (e) {
      console.warn("Failed to select inspector tick:", e);
    }
    // Phase 8.4.7 fix — let refreshTimeline() manage its own loading state
  }

  async inspectNpc(npcId) {
    setInspectorLoading(true);
    try {
      const setupPayload = this.getSetupPayload();
      const res = await inspectorClient.getNpcReasoning(setupPayload, npcId);
      rpgInspectorState.selectedNpcId = npcId;
      rpgInspectorState.npcReasoning = res.npc_reasoning;
      renderNpcReasoning(res.npc_reasoning);
      rpgInspectorState.causalTrace = buildCausalTrace({
        latestDiff: rpgInspectorState.latestDiff || {},
        timeline: rpgInspectorState.timeline || {},
        npcReasoning: res.npc_reasoning || {},
      });
      renderCausalTrace(rpgInspectorState.causalTrace);
    } catch (e) {
      console.warn("Failed to inspect NPC reasoning:", e);
    } finally {
      setInspectorLoading(false);
    }
  }

  populateNpcOptions() {
    const root = document.getElementById("rpg-inspector-npc-select");
    if (!root) return;
    const options = buildNpcOptions(this.getSimulationState());
    root.innerHTML = '<option value="">Select NPC</option>' + options.map(function(opt) {
      return '<option value="' + opt.npc_id + '"' + (opt.npc_id === rpgInspectorState.selectedNpcId ? ' selected' : '') + '>' + opt.label + '</option>';
    }).join("");
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
    setInspectorLoading(true);
    try {
      await inspectorClient.addDebugNote(setupPayload, note);
      const input = getEl("rpg-inspector-debug-note");
      if (input) input.value = "";
      await this.refreshAudit();
    } catch (e) {
      console.warn("Failed to add debug note:", e);
    } finally {
      setInspectorLoading(false);
    }
  }

  async refreshAudit() {
    const simulationState = this.getSimulationState();
    renderGmAudit((simulationState || {}).debug_meta || {});
    renderSseDiagnosticsPanel(rpgInspectorState.sseDiagnostics);
  }

  bind() {
    const saved = localStorage.getItem("rpg_inspector_open");
    if (saved === "1" || (!rpgInspectorState.timeline && saved !== "0")) {
      rpgInspectorState.isOpen = true;
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

    getEl("rpg-inspector-npc-select")?.addEventListener("change", async (e) => {
      const npcId = e.target.value || "";
      if (npcId) {
        const npcInput = getEl("rpg-inspector-npc-id");
        if (npcInput) npcInput.value = npcId;
        await this.inspectNpc(npcId);
      }
    });
    getEl("rpg-inspector-timeline-query")?.addEventListener("input", async (e) => {
      rpgInspectorState.timelineQuery = e.target.value || "";
      await this.refreshTimeline();
    });
    getEl("rpg-inspector-world-filter")?.addEventListener("change", async (e) => {
      rpgInspectorState.worldConsequenceFilter = e.target.value || "all";
      await this.refreshTimeline();
    });
    // Quick NPC inspect from timeline consequences
    window.addEventListener("rpg-inspector:inspectNpc", (e) => {
      if (e.detail) this.inspectNpc(e.detail);
    });

    if (!this._sseDiagBound) {
      window.addEventListener("rpg:sse_diagnostic", (e) => {
        this.handleSseDiagnostic(e.detail || {});
      });
      this._sseDiagBound = true;
    }

    renderSseDiagnosticsPanel(rpgInspectorState.sseDiagnostics);
  }
}

/* ─── Inventory filter helpers (Phase 9) ─── */

function rowMatchesFilter(row, activeFilter) {
  var timelineRow = row || {};
  var inventorySummary = timelineRow.inventory_summary || {};
  var hasInventory =
    Number(inventorySummary.last_loot_count || 0) > 0 ||
    Number(inventorySummary.total_item_qty || 0) > 0;

  if (activeFilter === "all") return true;
  if (activeFilter === "events") return Number(timelineRow.event_count || 0) > 0;
  if (activeFilter === "npcs") return Array.isArray(timelineRow.changed_npc_ids) && timelineRow.changed_npc_ids.length > 0;
  if (activeFilter === "gm") return Number(timelineRow.gm_action_count || 0) > 0;
  if (activeFilter === "inventory") return hasInventory;
  return true;
}
