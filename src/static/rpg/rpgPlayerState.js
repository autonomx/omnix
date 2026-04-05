/**
 * Phase 8 — Player State Management
 *
 * Extends existing RPG state with player_view and player_state containers.
 */

export const rpgPlayerState = {
  playerState: null,
  playerView: null,
};

export function updatePlayerViewFromResponse(data) {
  if (data && data.metadata && data.metadata.player_view) {
    rpgPlayerState.playerView = data.metadata.player_view;
    return data.metadata.player_view;
  }
  return null;
}

export function updatePlayerStateFromResponse(data) {
  if (data && data.player_state) {
    rpgPlayerState.playerState = data.player_state;
    return data.player_state;
  }
  return null;
}

export function getPlayerState() {
  return rpgPlayerState.playerState;
}

export function getPlayerView() {
  return rpgPlayerState.playerView;
}