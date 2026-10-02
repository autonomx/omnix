/* eslint-disable @typescript-eslint/no-unused-vars -- baseline WP-9.x */
/* eslint-disable no-restricted-imports -- baseline WP-9.x */
import type { OmnixModuleDefinition } from '../../app/modules';
import { SettingsControlCenter } from '../settings/SettingsControlCenter';

export function SettingsWorkspace({ module: _module }: { module: OmnixModuleDefinition }) {
  return <SettingsControlCenter />;
}
