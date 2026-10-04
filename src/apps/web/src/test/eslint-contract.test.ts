// @vitest-environment node
import { ESLint } from 'eslint';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const webRoot = fileURLToPath(new URL('../../', import.meta.url));

describe('web ESLint architecture rules', () => {
  const lintSource = async (source: string, filePath: string) => {
    const eslint = new ESLint({ cwd: webRoot });
    const [result] = await eslint.lintText(source, { filePath });
    return result.messages.map((message) => message.ruleId);
  };

  it('rejects a new fetch assignment in a source file', async () => {
    const ruleIds = await lintSource(
      'window.fetch = replacement;',
      'src/eslint-contract-fixture.ts',
    );

    expect(ruleIds).toContain('no-restricted-syntax');
  });

  it('rejects another feature deep import and allows its public index', async () => {
    const deepImportRuleIds = await lintSource(
      "import { TradingWorkspace } from '../trading/TradingWorkspace';",
      'src/features/storyteller/eslint-contract-fixture.ts',
    );
    const dynamicImportRuleIds = await lintSource(
      "void import('../trading/TradingWorkspace');",
      'src/features/storyteller/eslint-contract-fixture.ts',
    );
    const publicImportRuleIds = await lintSource(
      "import { TradingWorkspace } from '../trading';",
      'src/features/storyteller/eslint-contract-fixture.ts',
    );

    expect(deepImportRuleIds).toContain('no-restricted-imports');
    expect(dynamicImportRuleIds).toContain('omnix/no-cross-feature-dynamic-import');
    expect(publicImportRuleIds).not.toContain('no-restricted-imports');
  });

  it('rejects a feature import from core web code', async () => {
    const staticRuleIds = await lintSource(
      "import type { RpgNewGameRequest } from '../features/rpg/api/rpgSessionClient';",
      'src/api/eslint-contract-fixture.ts',
    );
    const dynamicRuleIds = await lintSource(
      "void import('../features/trading');",
      'src/events/eslint-contract-fixture.ts',
    );
    const coreRuleIds = await lintSource(
      "import { ApiError } from '../api/errors';",
      'src/events/eslint-contract-fixture.ts',
    );

    expect(staticRuleIds).toContain('omnix/no-core-feature-import');
    expect(dynamicRuleIds).toContain('omnix/no-core-feature-import');
    expect(coreRuleIds).not.toContain('omnix/no-core-feature-import');
  });

  it('allows the ModuleWorkspace shell and rejects direct application imports', async () => {
    const workspaceRuleIds = await lintSource(
      "import { ModuleWorkspace } from '../features/ModuleWorkspace';",
      'src/app/eslint-contract-fixture.ts',
    );
    const directFeatureRuleIds = await lintSource(
      "import { TradingWorkspace } from '../features/trading/TradingWorkspace';",
      'src/app/eslint-contract-fixture.ts',
    );
    const dynamicFeatureRuleIds = await lintSource(
      "void import('../features/trading/TradingWorkspace');",
      'src/app/eslint-contract-fixture.ts',
    );

    expect(workspaceRuleIds).not.toContain('no-restricted-imports');
    expect(directFeatureRuleIds).toContain('no-restricted-imports');
    expect(dynamicFeatureRuleIds).toContain('omnix/no-app-direct-feature-dynamic-import');
  });
});
