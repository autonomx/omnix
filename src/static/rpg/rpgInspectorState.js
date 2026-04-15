/**
 * Phase 8.4.6 — RPG Inspector State
 *
 * Shared state object for the RPG inspector panels.
 */

const rpgInspectorState = {
  timeline: null,
  latestDiff: null,
  selectedTick: null,
  selectedTickView: null,
  selectedNpcId: "",
  npcReasoning: null,
  timelineQuery: "",
  worldConsequenceFilter: "all",
  causalTrace: [],
  loading: false,
  isOpen: false,
  sseDiagnostics: {
    ambient: {
      status: "idle",
      connected: false,
      reconnectAttempts: 0,
      lastOpenAt: "",
      lastErrorAt: "",
      lastHeartbeatAt: "",
      lastMessageAt: "",
      lastSeq: 0,
      events: [],
    },
    narration: {
      status: "idle",
      connected: false,
      lastOpenAt: "",
      lastErrorAt: "",
      lastHeartbeatAt: "",
      lastMessageAt: "",
      activeTurnId: "",
      lastJobStatus: "",
      lastArtifactTurnId: "",
      events: [],
    },
  },
};

function resetInspectorState() {
  rpgInspectorState.timeline = null;
  rpgInspectorState.latestDiff = null;
  rpgInspectorState.selectedTick = null;
  rpgInspectorState.selectedTickView = null;
  rpgInspectorState.selectedNpcId = "";
  rpgInspectorState.npcReasoning = null;
  rpgInspectorState.timelineQuery = "";
  rpgInspectorState.worldConsequenceFilter = "all";
  rpgInspectorState.causalTrace = [];
  rpgInspectorState.loading = false;
  rpgInspectorState.sseDiagnostics = {
    ambient: {
      status: "idle",
      connected: false,
      reconnectAttempts: 0,
      lastOpenAt: "",
      lastErrorAt: "",
      lastHeartbeatAt: "",
      lastMessageAt: "",
      lastSeq: 0,
      events: [],
    },
    narration: {
      status: "idle",
      connected: false,
      lastOpenAt: "",
      lastErrorAt: "",
      lastHeartbeatAt: "",
      lastMessageAt: "",
      activeTurnId: "",
      lastJobStatus: "",
      lastArtifactTurnId: "",
      events: [],
    },
  };
}
