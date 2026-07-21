import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  rpgWorldAuthoringClient,
  type RpgAuthoringGroup,
  type RpgAuthoringSection,
} from '../../api/rpgWorldAuthoringClient';
import type { RpgWorldSummary } from '../../api/rpgWorldLibraryClient';
import { RpgWorldAdvancedPanel } from './RpgWorldAdvancedPanel';
import { RpgWorldAuthoringPage } from './RpgWorldAuthoringPage';
import {
  completeAuthoringSections,
  parseWorldEditorRoute,
  pushWorldEditorRoute,
} from './RpgWorldCompletionModels';
import { RpgWorldGenerationDashboard } from './RpgWorldGenerationDashboard';
import { RpgWorldImagesPanel } from './RpgWorldImagesPanel';
import { RpgWorldScenarioAuthoringPanel } from './RpgWorldScenarioAuthoringPanel';
import { RpgWorldVisualMapPanel } from './RpgWorldVisualMapPanel';
import './RpgWorldFinalizedDesign.css';
import './RpgWorldCompletionDesign.css';

interface RpgWorldEditorShellProps {
  onBack: () => void;
  onPlay: () => void;
  world: RpgWorldSummary;
  worldId: string;
}

const GROUPS: Array<{ id: RpgAuthoringGroup; label: string }> = [
  { id: 'workspace', label: 'Workspace' },
  { id: 'world', label: 'World' },
  { id: 'lore', label: 'Lore' },
  { id: 'game-master', label: 'Game Master' },
];

const DEDICATED_SECTIONS = ['advanced', 'generation', 'images', 'map', 'scenarios'];

function statusLabel(value: string): string {
  return value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function worldState(world: RpgWorldSummary): string {
  const generation = world.generation;
  if (world.status === 'archived') return 'Archived';
  if (generation?.status === 'running' || generation?.status === 'planned') return 'Generating';
  if (generation?.status === 'failed') return 'Generation failed';
  return world.status === 'published' ? 'Published' : 'Draft';
}

export function RpgWorldEditorShell({
  onBack,
  onPlay,
  world,
  worldId,
}: RpgWorldEditorShellProps) {
  const initialRoute = parseWorldEditorRoute();
  const queryClient = useQueryClient();
  const [sectionId, setSectionId] = useState(
    initialRoute?.worldId === worldId ? initialRoute.sectionId : 'overview',
  );
  const [entityId, setEntityId] = useState<string | null>(
    initialRoute?.worldId === worldId ? initialRoute.entityId ?? null : null,
  );
  const manifestQuery = useQuery({
    queryKey: ['feature', 'rpg', 'world-authoring-manifest', worldId],
    queryFn: () => rpgWorldAuthoringClient.manifest(worldId),
    refetchInterval: 5000,
  });
  const rawSections = manifestQuery.data?.sections ?? [];
  const sections = useMemo(() => completeAuthoringSections(rawSections), [rawSections]);
  const rawSectionIds = useMemo(() => new Set(rawSections.map((section) => section.id)), [rawSections]);
  const selectedSection = sections.find((section) => section.id === sectionId)
    ?? sections.find((section) => section.id === 'overview')
    ?? ({
      id: sectionId,
      label: statusLabel(sectionId),
      group: 'workspace',
      page_kind: 'document',
      topic_ids: [],
      dependencies: [],
      required_before_launch: false,
      supports_generation: false,
      supports_images: false,
      supports_entity_editing: false,
      operational_status: 'empty',
      editorial_status: 'unreviewed',
      entity_count: 0,
    } satisfies RpgAuthoringSection);
  const pageQuery = useQuery({
    queryKey: ['feature', 'rpg', 'world-authoring-section', worldId, selectedSection.id],
    queryFn: () => rpgWorldAuthoringClient.section(worldId, selectedSection.id),
    enabled: Boolean(worldId)
      && !DEDICATED_SECTIONS.includes(selectedSection.id)
      && rawSectionIds.has(selectedSection.id),
    refetchInterval: selectedSection.operational_status === 'generating' ? 3000 : false,
  });

  const navigate = (nextSectionId: string, nextEntityId: string | null = null, replace = false) => {
    setSectionId(nextSectionId);
    setEntityId(nextEntityId);
    pushWorldEditorRoute({ worldId, sectionId: nextSectionId, entityId: nextEntityId ?? undefined }, replace);
  };

  useEffect(() => {
    const syncRoute = () => {
      const route = parseWorldEditorRoute();
      if (!route || route.worldId !== worldId) return;
      setSectionId(route.sectionId || 'overview');
      setEntityId(route.entityId ?? null);
    };
    window.addEventListener('popstate', syncRoute);
    window.addEventListener('hashchange', syncRoute);
    return () => {
      window.removeEventListener('popstate', syncRoute);
      window.removeEventListener('hashchange', syncRoute);
    };
  }, [worldId]);

  useEffect(() => {
    if (sections.length && !sections.some((section) => section.id === sectionId)) {
      navigate(sections[0].id, null, true);
    }
  }, [sectionId, sections]);

  useEffect(() => {
    const route = parseWorldEditorRoute();
    if (!route || route.worldId !== worldId) navigate(sectionId, entityId, true);
  }, [worldId]);

  const updateWorld = useMutation({
    mutationFn: (changes: Record<string, unknown>) => rpgWorldAuthoringClient.updateWorld(worldId, {
      expected_draft_revision: (manifestQuery.data?.world ?? world).draft_revision,
      ...changes,
    }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-authoring-manifest', worldId] }),
        queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-authoring-section', worldId] }),
        queryClient.invalidateQueries({ queryKey: ['feature', 'rpg', 'world-authoring-workspace'] }),
      ]);
    },
  });

  const grouped = useMemo(() => new Map(GROUPS.map((group) => [
    group.id,
    sections.filter((section) => section.group === group.id),
  ])), [sections]);
  const currentWorld = manifestQuery.data?.world ?? world;

  return (
    <section className="rpg-authoring-editor" aria-label="World editor">
      <header className="rpg-authoring-editor-header">
        <div><button className="rpg-secondary-button" type="button" onClick={onBack}>Back to Worlds</button><span>/</span><strong>{currentWorld.title}</strong>{entityId ? <><span>/</span><span>{statusLabel(entityId)}</span></> : null}</div>
        <div><span>{worldState(currentWorld)}</span><button type="button" onClick={onPlay}>Play</button></div>
      </header>
      <div className="rpg-authoring-editor-layout">
        <nav aria-label="World editor sections">
          {GROUPS.map((group) => {
            const rows = grouped.get(group.id) ?? [];
            if (!rows.length) return null;
            return (
              <section key={group.id}>
                <h4>{group.label}</h4>
                {rows.map((section) => (
                  <button
                    className={selectedSection.id === section.id ? 'is-active' : ''}
                    key={section.id}
                    type="button"
                    onClick={() => navigate(section.id)}
                  >
                    <span>{section.label}</span>
                    <small>{statusLabel(section.operational_status)}{section.entity_count ? ` · ${section.entity_count}` : ''}</small>
                  </button>
                ))}
              </section>
            );
          })}
          {manifestQuery.isPending ? <p>Loading sections…</p> : null}
          {manifestQuery.isError ? <p className="rpg-world-catalog-error">Unable to load authoring manifest.</p> : null}
        </nav>
        <main>
          {selectedSection.id === 'advanced' ? (
            <RpgWorldAdvancedPanel world={currentWorld} />
          ) : selectedSection.id === 'generation' ? (
            <RpgWorldGenerationDashboard
              generation={manifestQuery.data?.generation}
              onOpenImages={() => navigate('images')}
              sections={sections}
              worldId={worldId}
            />
          ) : selectedSection.id === 'images' ? (
            <RpgWorldImagesPanel worldId={worldId} />
          ) : selectedSection.id === 'map' ? (
            <RpgWorldVisualMapPanel worldId={worldId} />
          ) : selectedSection.id === 'scenarios' ? (
            <RpgWorldScenarioAuthoringPanel worldId={worldId} />
          ) : (
            <RpgWorldAuthoringPage
              error={pageQuery.error instanceof Error ? pageQuery.error.message : undefined}
              isLoading={pageQuery.isPending && rawSectionIds.has(selectedSection.id)}
              isSaving={updateWorld.isPending}
              onOpenSection={(nextSectionId) => navigate(nextSectionId)}
              onSaveWorld={(changes) => updateWorld.mutate(changes)}
              onSelectEntity={(nextEntityId) => navigate(selectedSection.id, nextEntityId)}
              page={pageQuery.data}
              section={selectedSection}
              sections={sections}
              selectedEntityId={entityId}
              world={currentWorld}
              worldId={worldId}
            />
          )}
        </main>
      </div>
    </section>
  );
}
