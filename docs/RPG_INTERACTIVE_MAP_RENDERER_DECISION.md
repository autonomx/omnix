# RPG Interactive Map Renderer Decision — MAP-13

Status: SVG retained for the production baseline, with a deterministic PixiJS escalation gate.

## Decision

The interactive RPG map continues to use the React/SVG renderer for the default world, region, settlement, interior, and encounter map targets.

SVG is retained because the current contracts and starter content remain well below the explicit render budgets, while SVG provides:

- native keyboard-focusable map objects;
- accessible labels and roles;
- deterministic DOM ordering;
- straightforward hitboxes, tooltips, and reduced-motion behavior;
- no second rendering runtime or duplicate interaction system.

PixiJS is not added speculatively. The server-side `map_performance` decision gate recommends Pixi only when a definition or overlay exceeds one or more measured complexity budgets.

## Versioned SVG budgets

Decision version 1 uses these default upper bounds:

| Metric | SVG budget |
| --- | ---: |
| Map objects | 320 |
| Routes | 180 |
| Route points | 5,000 |
| Labels | 240 |
| Markers | 320 |
| Fog polygons | 96 |
| Canonical definition bytes | 1,500,000 |

The assessment is deterministic and reports every exceeded metric. It does not silently change renderers based on device identity or timing noise.

## Browser work reduction

The frontend includes deterministic logical-coordinate viewport culling for:

- object sprites;
- route polylines;
- labels;
- markers.

Culling uses the inverse viewport transform with bounded overscan. Source order is preserved, so SVG output remains deterministic. Accessible object navigation remains backed by the full visible/discovered object projection rather than only the current visual cull set.

## PixiJS promotion criteria

A PixiJS implementation should be introduced only when both conditions are met:

1. Representative production content exceeds at least one versioned SVG budget or measured interaction profiling shows sustained frame misses after culling.
2. The Pixi implementation preserves the existing authoritative contracts, hitbox semantics, keyboard navigation, screen-reader alternative list, deterministic ordering, reduced-motion behavior, and test coverage.

Recommended measured promotion signal:

- p95 pan/zoom frame time above 16.7 ms on the supported baseline device;
- after image decode is complete;
- with representative maximum-budget content;
- across at least three repeat runs;
- while the SVG culling path is enabled.

## Non-goals

MAP-13 does not:

- select a renderer from user-agent strings;
- allow renderer choice to affect simulation or map action truth;
- remove SVG fallback rendering;
- treat a large asset file alone as proof that PixiJS is needed;
- hide budget overruns.

## Release implication

The current starter region, settlement, and interior maps are expected to remain on SVG. Procedurally assembled settlements are validated against the same decision gate. Any future content that receives a `pixi` recommendation must either be reduced to budget or shipped with the separately verified Pixi renderer before release.
