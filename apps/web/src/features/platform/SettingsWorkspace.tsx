import type { OmnixModuleDefinition } from '../../app/modules';
import { WorkspacePanel } from '../../design/primitives';
import { HermesReviewCard } from './HermesReviewCard';
import { HermesStatusCard } from './HermesStatusCard';
import { PlatformModuleWorkspace } from './PlatformModuleWorkspace';

export function SettingsWorkspace({ module }: { module: OmnixModuleDefinition }) {
  return (
    <>
      <WorkspacePanel>
        <HermesStatusCard />
        <HermesReviewCard />
      </WorkspacePanel>
      <PlatformModuleWorkspace module={module} />
    </>
  );
}
