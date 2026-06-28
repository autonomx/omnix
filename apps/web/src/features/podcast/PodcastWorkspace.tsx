// @ts-nocheck
import type { OmnixModuleDefinition } from '../../app/modules';
export function PodcastWorkspace({ module }: { module: OmnixModuleDefinition }) {
  return <section><h2>{module.label}</h2><h3>1. Episode setup</h3><label>Episode brief<textarea /></label><button type="button">Generate live podcast</button></section>;
}
