import { mergeConfig } from 'vitest/config';

import webConfig from './vitest.config';

export default mergeConfig(webConfig, {
  test: {
    setupFiles: 'src/apps/web/src/test/setup.ts',
  },
});
