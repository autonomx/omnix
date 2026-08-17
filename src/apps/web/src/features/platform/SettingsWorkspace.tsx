import type { OmnixModuleDefinition } from '../../app/modules';
import { SettingsControlCenter } from '../settings/SettingsControlCenter';

export function SettingsWorkspace({ module: _module }: { module: OmnixModuleDefinition }) {
  return <SettingsControlCenter />;
}
