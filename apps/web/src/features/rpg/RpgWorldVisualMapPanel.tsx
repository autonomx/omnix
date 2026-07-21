import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { rpgWorldLibraryClient } from '../../api/rpgWorldLibraryClient';
import { RpgWorldMapAuthoringPanel } from './RpgWorldMapAuthoringPanel';
import { record, text, worldLocationOptions } from './rpgWorldAuthoringData';

interface RpgWorldVisualMapPanelProps {
  worldId: string;
}

function coordinate(index: number, total: number): { left: string; top: string } {
  const angle = (Math.PI * 2 * index) / Math.max(total, 1) - Math.PI / 2;
  const radius = total > 8 ? 39 : 34;
  return {
    left: `${50 + Math.cos(angle) * radius}%`,
    top: `${50 + Math.sin(angle) * radius}%`,
  };
}

export function RpgWorldVisualMapPanel({ worldId }: RpgWorldVisualMapPanelProps) {
  const [selectedLocationId, setSelectedLocationId] = useState('');
  const detailQuery = useQuery({
    queryKey: ['feature', 'rpg', 'world-library', 'visual-map', worldId],
    queryFn: () => rpgWorldLibraryClient.detail(worldId),
    refetchInterval: 5000,
  });
  const detail = detailQuery.data;
  const locations = useMemo(() => worldLocationOptions(detail), [detail]);
  const selected = locations.find((location) => location.id === selectedLocationId) ?? locations[0];
  const blueprints = detail?.map_blueprints ?? [];
  const selectedBlueprint = blueprints.find((blueprint) => text(record(blueprint.document).location_id) === selected?.id);

  return (
    <div className="rpg-visual-map-page">
      <section className="rpg-authoring-page rpg-visual-map-browser" aria-label="Visual world map">
        <div className="rpg-authoring-page-heading">
          <div><p className="eyebrow">World atlas</p><h2>Map</h2><p>Browse authored Areas visually, then open the semantic blueprint editor when precise map data needs revision.</p></div>
          <span>{locations.length} areas · {blueprints.filter((row) => row.status === 'ready').length} ready blueprints</span>
        </div>
        {detailQuery.isPending ? <p>Loading world atlas…</p> : null}
        {detailQuery.isError ? <p className="rpg-world-catalog-error">Unable to load the world atlas.</p> : null}
        {!detailQuery.isPending && !locations.length ? <div className="rpg-authoring-empty"><h3>No mapped areas yet</h3><p>Generate Areas before building the visual atlas.</p></div> : null}
        {locations.length ? (
          <div className="rpg-visual-map-layout">
            <div className="rpg-visual-map-canvas" role="img" aria-label="Semantic area map">
              <div className="rpg-visual-map-center"><strong>World</strong><small>{detail?.world.title}</small></div>
              {locations.map((location, index) => {
                const position = coordinate(index, locations.length);
                const blueprint = blueprints.find((row) => text(record(row.document).location_id) === location.id);
                return (
                  <button
                    className={selected?.id === location.id ? 'is-active' : ''}
                    key={location.id}
                    style={position}
                    type="button"
                    onClick={() => setSelectedLocationId(location.id)}
                  >
                    <span>{location.label.slice(0, 1).toUpperCase()}</span>
                    <strong>{location.label}</strong>
                    <small>{blueprint?.status ?? 'unmapped'}</small>
                  </button>
                );
              })}
            </div>
            <aside className="rpg-visual-map-inspector">
              <p className="eyebrow">Selected area</p>
              <h3>{selected?.label}</h3>
              <dl>
                <div><dt>Area ID</dt><dd>{selected?.id}</dd></div>
                <div><dt>Blueprint</dt><dd>{selectedBlueprint?.map_id ?? 'Not authored'}</dd></div>
                <div><dt>Status</dt><dd>{selectedBlueprint?.status ?? 'Needs blueprint'}</dd></div>
                <div><dt>Revision</dt><dd>{selectedBlueprint?.blueprint_revision ?? '—'}</dd></div>
              </dl>
              {selectedBlueprint?.findings.length ? <p className="rpg-world-catalog-error">{selectedBlueprint.findings.length} reconciliation finding(s) need review.</p> : <p>{selectedBlueprint ? 'All active references reconcile.' : 'Open authoring tools to create the first semantic blueprint.'}</p>}
            </aside>
          </div>
        ) : null}
        {locations.length ? (
          <div className="rpg-visual-map-gallery">
            {locations.map((location) => (
              <button key={location.id} type="button" onClick={() => setSelectedLocationId(location.id)}>
                <span>{location.label.slice(0, 1).toUpperCase()}</span><strong>{location.label}</strong><small>{blueprints.some((row) => text(record(row.document).location_id) === location.id) ? 'Blueprint available' : 'Needs blueprint'}</small>
              </button>
            ))}
          </div>
        ) : null}
      </section>
      <details className="rpg-visual-map-authoring">
        <summary>Open semantic blueprint authoring</summary>
        <RpgWorldMapAuthoringPanel worldId={worldId} />
      </details>
    </div>
  );
}
