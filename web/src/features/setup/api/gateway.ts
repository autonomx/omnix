import type { paths as CorePaths } from '../../../api/generated/core';
import { createGatewayClient } from '../../../api/http';
import type { paths } from './generated';

/** The setup feature's typed gateway client: the model-pack operations it uses and the kernel's (PA-2.4). */
export const api = createApi();

/** The same client over another fetch (tests, calls that skip fetch middleware). */
export function createApi(options: { baseUrl?: string; fetchImpl?: typeof fetch } = {}) {
  return createGatewayClient<CorePaths & paths>(options);
}
