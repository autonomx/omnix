import type { OmnixModuleDefinition } from '../../app/modules';
import { WorkspacePanel } from '../../design/primitives';
import { HermesStatusCard } from './HermesStatusCard';
import { InfoCard } from './InfoCard';
import { PlatformModuleWorkspace } from './PlatformModuleWorkspace';

export function SettingsWorkspace({ module }: { module: OmnixModuleDefinition }) {
  return (
    <>
      <WorkspacePanel>
        <HermesStatusCard />
        <InfoCard
          title="Setup"
          summary="Check the suggested setup guidance before continuing."
          area="Settings"
          state="pending"
        />
      </WorkspacePanel>
      <PlatformModuleWorkspace module={module} />
    </>
  );
}
