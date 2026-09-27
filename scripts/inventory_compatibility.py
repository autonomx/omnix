"""Refresh the reviewed compatibility allowlist and caller inventory."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
DISPOSITIONS = {
    'runtime_document_compat': ('B', 'Shared document callback and legacy behavior composition', 'Inject a settings/session service into shared.py, then split stable stores from legacy callback adapters.'),
    'rpg_compat': ('B', 'Legacy RPG session and interaction function contracts', 'Move callers to an explicit session repository; preserve payload normalization and atomic writes.'),
    'rpg_feature_compat': ('B', 'Legacy NPC projection and narrative event contracts', 'Use typed NPC/narrative repositories and migrate default factories before deleting wrappers.'),
    'image_asset_compat': ('B', 'Legacy image manifest function contracts', 'Move image callers to the shared asset service; retain artifact files outside structured authority.'),
    'configuration_compat': ('B', 'Legacy assistant policy and tool configuration functions', 'Move consumers to typed configuration services; preserve secret-store boundaries.'),
    'inline_execution_compat': ('A', 'Normalizes the inline execution marker used by durable job admission', 'Keep this stable job contract adapter; rename when its public import paths can be migrated together.'),
}


def main():
    sources = {path: path.read_text(encoding='utf-8-sig') for base in ('src/app', 'src/tests') for path in (ROOT / base).rglob('*.py')}
    modules = []
    for path in sorted((ROOT / 'src/app').rglob('*_compat.py')):
        default = (
            'A', 'Stable PostgreSQL implementation of an existing domain service contract',
            'Keep the behavior adapter; rename away from compat only after all listed imports and tests migrate together.',
        )
        if 'platform' in path.parts:
            default = ('B', 'Gateway payload facade over RPG domain services',
                       'Move gateway imports to typed RPG services, preserving HTTP payload contracts; then delete this facade.')
        elif path.stem == 'flux_pipeline_compat':
            default = ('A', 'Adapts supported Diffusers/Flux pipeline versions and fallback call signatures',
                       'Keep while supported compute stacks differ; rename only when both image and RPG visual imports migrate together.')
        category, purpose, prerequisite = DISPOSITIONS.get(path.stem, default)
        pattern = re.compile(r'(?:\.|import\s+)' + re.escape(path.stem) + r'\b')
        callers = [caller.relative_to(ROOT).as_posix() for caller, source in sources.items() if caller != path and pattern.search(source)]
        modules.append({'path': path.relative_to(ROOT).as_posix(), 'category': category, 'purpose': purpose,
                        'production_call_sites': [name for name in callers if name.startswith('src/app/')],
                        'tests': [name for name in callers if name.startswith('src/tests/')],
                        'replacement_or_deletion_prerequisite': prerequisite})
    output = ROOT / 'docs/architecture/compatibility-inventory.json'
    output.write_text(json.dumps({'schema_version': 1, 'modules': modules}, indent=2) + '\n', encoding='utf-8')
    print(f'Inventoried {len(modules)} compatibility modules')


if __name__ == '__main__':
    main()
