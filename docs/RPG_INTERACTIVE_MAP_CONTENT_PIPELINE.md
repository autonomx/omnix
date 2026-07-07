# RPG interactive map content pipeline

MAP-18 provides a stateless definition-authoring pipeline. It validates and transforms candidate map JSON without writing to the production definition repository or mutating a campaign.

## API

### Validate

`POST /api/rpg/map-editor/validate`

```json
{
  "definition": {},
  "context": {
    "canonical_route_ids": [],
    "known_map_ids": [],
    "allowed_asset_ids": []
  }
}
```

The response contains deterministic canonical JSON, a content revision, and path-addressed errors or warnings.

### Apply edit operations

`POST /api/rpg/map-editor/apply`

Supported operations:

- `move_object`
- `assign_object_asset`
- `set_object_polygon` for `footprint` or `hitbox`
- `set_child_map`
- `upsert_route`
- `remove_route`
- `set_background_asset`

The service applies operations to a deep copy, validates the result, and returns the transformed definition and report. No repository file or session is changed.

### Export

`POST /api/rpg/map-editor/export`

A valid candidate is returned as stable, formatted JSON with an attachment filename and `X-Map-Definition-Revision` header. Invalid content returns the validation report with status 422.

## Validation boundaries

The validator checks:

- required map identity, level, and positive logical bounds;
- stable unique object, route, and label IDs;
- integer object positions and route/polygon coordinates;
- hitboxes for interactive objects;
- minimum polygon and route point counts;
- object sprite IDs and dimensions;
- optional allowlists for assets, canonical route IDs, parent maps, and child maps;
- deterministic canonical serialization and content revision.

The pipeline never derives canonical IDs from labels, never reads local paths from candidate JSON, and never publishes a candidate automatically. A reviewed exported definition must still be added through the normal repository workflow and pass the existing deterministic PR gates.

## Suggested authoring workflow

1. Load an existing definition through the map definition API.
2. Submit narrow edit operations.
3. Render the returned candidate in the existing SVG map renderer or another preview client.
4. Correct all errors and review warnings.
5. Export canonical JSON.
6. Add the definition to the repository in a dedicated content PR.
7. Run exact-head architecture and deterministic checks before merge.
