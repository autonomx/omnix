/**
 * Phase 8 — Frontend Integration
 *
 * Hooks player-facing UX into the existing RPG game loop.
 * Primary UX loop: simulation -> scene -> narrator -> player_view -> UI render
 */

import { RPGPlayerClient } from "./rpgPlayerClient.js";
import { RPGDialogueClient } from "./rpgDialogueClient.js";
import { rpgPlayerState, updatePlayerViewFromResponse, updatePlayerStateFromResponse } from "./rpgPlayerState.js";
import { renderPlayerView } from "./rpgPlayerRenderer.js";
import { loadJournal, loadCodex, loadObjectives, handleEnterDialogue, handleExitDialogue, refreshSidePanels, bindDialogueInput } from "./rpgPlayerUI.js";
import { renderDialogueState, renderSuggestedReplies, appendDialogueReply, clearDialogueUI } from "./rpgDialogueRenderer.js";

// Phase 8.4.6 — Inspector integration
import { RPGInspectorUI } from "./rpgInspectorUI.js";

export class RPGPlayerIntegration {
  constructor(setupPayload = null) {
    this.setupPayload = setupPayload;
    this.playerClient = new RPGPlayerClient();
    this.dialogueClient = new RPGDialogueClient();
    this.inspectorUI = null; // Phase 8.4.6 — Inspector UI instance
    this._inspectorRefreshTimer = null; // Phase 8.4.6 fix — debounce refresh
    bindDialogueInput((text) => this.sendDialogueMessage(text));
  }

  // Phase 8.4.6 — Bootstrap hooks for inspector
  ensureInspector() {
    if (this.inspectorUI) return this.inspectorUI;
    this.inspectorUI = new RPGInspectorUI(
      () => this.setupPayload || {},
      () => {
        const meta = (this.setupPayload || {}).metadata || {};
        return meta.simulation_state || {};
      }
    );
    this.inspectorUI.bind();
    return this.inspectorUI;
  }

  // Phase 8.4.6 — Debounced helper to refresh inspector after state changes
  _refreshInspector() {
    if (this._inspectorRefreshTimer) {
      clearTimeout(this._inspectorRefreshTimer);
    }
    this._inspectorRefreshTimer = setTimeout(async () => {
      const inspector = this.ensureInspector();
      await inspector.refreshTimeline();
      await inspector.refreshAudit();
    }, 50);
  }

  setSetupPayload(payload) {
    this.setupPayload = payload;
  }

  /**
   * Capture player_view from narrator response and render it.
   * Call this after each action response.
   */
  processResponse(data) {
    if (!data) return;

    // Capture player_view from metadata
    const playerView = updatePlayerViewFromResponse(data);
    if (playerView) {
      renderPlayerView(playerView);
    }

    // Update player state if present
    if (data.player_state) {
      updatePlayerStateFromResponse(data);
    }
  }

  /**
   * Enter dialogue mode with an NPC.
   */
  async enterDialogue(npcId, sceneId) {
    if (!this.setupPayload) {
      console.warn("No setup payload available for dialogue");
      return null;
    }
    const result = await handleEnterDialogue(this.setupPayload, npcId, sceneId);
    if (result) {
      this.setupPayload = result.setupPayload;
      rpgPlayerState.playerState = result.playerState;
      await this._refreshInspector();
    }
    return result;
  }

  /**
   * Exit dialogue mode.
   */
  async exitDialogue() {
    if (!this.setupPayload) {
      console.warn("No setup payload available for exit dialogue");
      return null;
    }
    const result = await handleExitDialogue(this.setupPayload);
    if (result) {
      this.setupPayload = result.setupPayload;
      rpgPlayerState.playerState = result.playerState;
      await this._refreshInspector();
    }
    return result;
  }

  async startDialogue(npcId, sceneId) {
    if (!this.setupPayload) return null;
    const result = await this.dialogueClient.start(this.setupPayload, npcId, sceneId);
    if (result) {
      this.setupPayload = result.setup_payload;
      rpgPlayerState.playerState = rpgPlayerState.playerState || {};
      rpgPlayerState.playerState.dialogue_state = result.dialogue_state;
      renderDialogueState(result.dialogue_state);
      renderSuggestedReplies(result.dialogue_state, (text) => this.sendDialogueMessage(text));
      await this._refreshInspector();
    }
    return result;
  }

  async sendDialogueMessage(message) {
    if (!this.setupPayload) return null;
    const playerState = rpgPlayerState.playerState || {};
    const dialogueState = playerState.dialogue_state || {};
    const npcId = dialogueState.npc_id || playerState.active_npc_id || "";
    const sceneId = dialogueState.scene_id || playerState.current_scene_id || "";
    if (!npcId) return null;

    const result = await this.dialogueClient.sendMessage(
      this.setupPayload,
      npcId,
      sceneId,
      message
    );

    if (result) {
      this.setupPayload = result.setup_payload;
      rpgPlayerState.playerState = rpgPlayerState.playerState || {};
      rpgPlayerState.playerState.dialogue_state = result.dialogue_state;
      renderDialogueState(result.dialogue_state);
      renderSuggestedReplies(result.dialogue_state, (text) => this.sendDialogueMessage(text));
      appendDialogueReply(result.reply);
      await this._refreshInspector();
    }
    return result;
  }

  async endDialogueSession() {
    if (!this.setupPayload) return null;
    const result = await this.dialogueClient.end(this.setupPayload);
    if (result) {
      this.setupPayload = result.setup_payload;
      rpgPlayerState.playerState = rpgPlayerState.playerState || {};
      rpgPlayerState.playerState.dialogue_state = result.dialogue_state;
      clearDialogueUI();
      await this._refreshInspector();
    }
    return result;
  }

  /**
   * Refresh all side panels (journal, codex, objectives).
   */
  async refreshSidePanels() {
    if (!this.setupPayload) return;
    return refreshSidePanels(this.setupPayload);
  }

  /**
   * Load journal entries.
   */
  async loadJournal() {
    if (!this.setupPayload) return [];
    return loadJournal(this.setupPayload);
  }

  /**
   * Load codex entries.
   */
  async loadCodex() {
    if (!this.setupPayload) return {};
    return loadCodex(this.setupPayload);
  }

  /**
   * Load player objectives.
   */
  async loadObjectives() {
    if (!this.setupPayload) return [];
    return loadObjectives(this.setupPayload);
  }

  /**
   * Build encounter view for a scene.
   */
  async buildEncounter(scene) {
    if (!this.setupPayload) return null;
    return this.playerClient.buildEncounter(this.setupPayload, scene);
  }

  /**
   * Get current player state.
   */
  getPlayerState() {
    return rpgPlayerState.playerState;
  }

  /**
   * Get current player view.
   */
  getPlayerView() {
    return rpgPlayerState.playerView;
  }
}