import type { OmnixModuleDefinition } from '../../app/modules';
import { WorkspacePanel } from '../../design/primitives';
import { HermesRecentPanel as Recent } from './HermesRecentPanel';
import { HermesReviewCard } from './HermesReviewCard';
import { HermesStatusCard } from './HermesStatusCard';
import { PlatformModuleWorkspace } from './PlatformModuleWorkspace';

export function SettingsWorkspace({ module }: { module: OmnixModuleDefinition }) {
  return (
    <>
      <WorkspacePanel>
        <HermesStatusCard />
        <HermesReviewCard />
        <Recent />
      </WorkspacePanel>
      <PlatformModuleWorkspace module={module} />
    </>
  );
}
