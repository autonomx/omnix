/**
 * Phase 8.4.7 — RPG Inspector Filters
 *
 * Filter utilities for the inspector UI:
 * - Timeline snapshot filtering
 * - World consequence type filtering
 * - NPC options building for dropdown
 */

export function filterTimelineSnapshots(snapshots, query) {
  const q = String(query || "").trim().toLowerCase();
  const rows = Array.isArray(snapshots) ? snapshots : [];
  if (!q) return rows;
  return rows.filter((row) => {
    const tick = String(row?.tick ?? "");
    const label = String(row?.label ?? "").toLowerCase();
    const snapshotId = String(row?.snapshot_id ?? "").toLowerCase();
    return tick.includes(q) || label.includes(q) || snapshotId.includes(q);
  });
}

export function filterWorldConsequences(items, typeFilter) {
  const rows = Array.isArray(items) ? items : [];
  const t = String(typeFilter || "").trim().toLowerCase();
  if (!t || t === "all") return rows;
  return rows.filter((item) => String(item?.type || "").toLowerCase() === t);
}

export function buildNpcOptions(simulationState) {
  const npcIndex = ((simulationState || {}).npc_index || {});
  return Object.keys(npcIndex)
    .sort((a, b) => {
      const na = String(npcIndex[a]?.name || a).toLowerCase();
      const nb = String(npcIndex[b]?.name || b).toLowerCase();
      if (na < nb) return -1;
      if (na > nb) return 1;
      return String(a).localeCompare(String(b));
    })
    .map((npcId) => ({
      npc_id: npcId,
      label: `${npcIndex[npcId]?.name || npcId} (${npcId})`,
    }));
}