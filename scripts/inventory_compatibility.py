"""Refresh the reviewed compatibility allowlist and caller inventory."""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
# Reviewed dispositions by module stem; a module without one gets the default below.
DISPOSITIONS: dict[str, tuple[str, str, str]] = {}


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
