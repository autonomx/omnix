 .../rpg-phase83-sandbox-fixpass-20260405-0106.diff | 1358 +++++++++++++
 .../rpg-phase84-gm-inspection-20260405-0158.diff   | 1111 +++++++++++
 .../rpg-phase84-gm-inspection-20260405-0158.md     |   76 +
 .../rpg-phase85-save-migration-20260405-0118.diff  | 1112 +++++++++++
 .../rpg-phase85-save-migration-20260405-0118.md    |   99 +
 ...ase85-save-migration-fixpass-20260405-0128.diff | 2023 ++++++++++++++++++++
 ...phase85-save-migration-fixpass-20260405-0128.md |   97 +
 rpg-design.txt                                     | 1019 ++++++----
 src/app/__init__.py                                |    2 +
 src/app/rpg/analytics/__init__.py                  |   18 +
 src/app/rpg/analytics/gm_hooks.py                  |   52 +
 src/app/rpg/analytics/npc_reasoning.py             |   54 +
 src/app/rpg/analytics/tick_diff.py                 |  101 +
 src/app/rpg/analytics/timeline.py                  |   67 +
 src/app/rpg/api/rpg_inspection_routes.py           |  132 ++
 src/app/rpg/creator/world_debug.py                 |    3 +
 src/app/rpg/creator/world_simulation.py            |   15 +
 .../functional/test_phase84_inspection_routes.py   |  112 ++
 src/tests/regression/test_phase                    |  151 ++
 src/tests/unit/rpg/test_phase84_npc_reasoning.py   |   41 +
 src/tests/unit/rpg/test_phase84_tick_diff.py       |   79 +
 21 files changed, 7305 insertions(+), 417 deletions(-)
"Phase 8.4 Fix Pass - 2026-04-05 02:15"  
"## Fixes Applied"  
""  
"### BUG 1 - Timeline snapshot mismatch"  
"Fixed timeline.py to read snapshots from timeline.ticks instead of simulation_state.snapshots"  
""  
"### BUG 2 - tick_diff assumes append-only lists"  
"Implemented ID-based diff with hybrid fallback for items without IDs"  
""  
"### BUG 3 - GM hooks bypass simulation invariants"  
"Normalized goal structure in gm_force_npc_goal with goal_id/type/priority"  
""  
"### BUG 4 - timeline_tick returns empty silently"  
"Added found boolean to get_timeline_tick response"  
""  
"### IMPROVEMENT 1 - Add diff summary"  
"Added summary object with event_delta/consequence_delta/npc_changes"  
""  
"### IMPROVEMENT 2 - NPC reasoning stability ordering"  
"Goals sorted by goal_id for deterministic output"  
""  
"### IMPROVEMENT 3 - GM actions audit trail"  
"Added gm_audit log in debug_meta for force_npc_goal and append_debug_note"  
""  
"### IMPROVEMENT 4 - Expose tick_diff via timeline API"  
"Added latest_diff to inspect_timeline response using last two ticks"  
""  
"## Test Results: 13 passed"  
