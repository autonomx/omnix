import type { ComponentProps, ReactNode } from 'react';
import { FeatureSubmitFeedback } from '../../shared/FeatureSubmitFeedback';
import { RpgGameMasterPanel } from './RpgGameMasterPanel';
import { RpgLoadoutTabs } from './RpgLoadoutTabs';
import { RpgNarrativeTabs, type RpgNarrativeTab } from './RpgNarrativeTabs';
import type { RpgPlayPanelId } from './RpgPlayPanels';
import { RpgSurvivalCard } from './RpgSurvivalCard';
import type { RpgHeroSummaryPreview, RpgSurvivalPreview } from './rpgUiTypes';
import { RpgVoicesPanel } from './RpgVoicesPanel';
import { RpgWorldPanel } from './RpgWorldPanel';

interface RpgPlayPanelContentProps {
  heroSummary: RpgHeroSummaryPreview;
  journal: Omit<ComponentProps<typeof RpgNarrativeTabs>, 'initialTab'>;
  journalTab: RpgNarrativeTab;
  loadout: Omit<ComponentProps<typeof RpgLoadoutTabs>, 'section' | 'statusPanel'>;
  loadoutFeedback: Pick<ComponentProps<typeof FeatureSubmitFeedback>, 'error' | 'isError' | 'isPending'>;
  onSelectCommand: (command: string) => void;
  panel: RpgPlayPanelId | null;
  survival: RpgSurvivalPreview;
  /** The map and who is here, on a screen too narrow to keep them beside the story. */
  worldHere?: ReactNode;
  world: Omit<ComponentProps<typeof RpgWorldPanel>, 'here' | 'onSelectCommand'>;
}

/** What each of the play bar's panels holds. */
export function RpgPlayPanelContent({
  heroSummary, journal, journalTab, loadout, loadoutFeedback, onSelectCommand, panel, survival, world, worldHere,
}: RpgPlayPanelContentProps) {
  return (
    <>
      {panel === 'pack' ? <RpgLoadoutTabs {...loadout} section="pack" /> : null}
      {panel === 'character' ? (
        <RpgLoadoutTabs
          {...loadout}
          section="character"
          statusPanel={(
            <div className="rpg-character-status">
              <p>{heroSummary.subtitle} · {heroSummary.origin}</p>
              <RpgSurvivalCard onSelectCommand={onSelectCommand} survival={survival} />
            </div>
          )}
        />
      ) : null}
      {panel === 'pack' || panel === 'character' ? (
        <FeatureSubmitFeedback
          {...loadoutFeedback}
          errorPrefix="Your inventory"
          pendingMessage="Working on it…"
          successPrefix="Done"
        />
      ) : null}
      {panel === 'journal' ? <RpgNarrativeTabs {...journal} initialTab={journalTab} key={journalTab} /> : null}
      {panel === 'world' ? <RpgWorldPanel {...world} here={worldHere} onSelectCommand={onSelectCommand} /> : null}
      {panel === 'game-master' ? <RpgGameMasterPanel /> : null}
      {panel === 'voices' ? <RpgVoicesPanel /> : null}
    </>
  );
}
