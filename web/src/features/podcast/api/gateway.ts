import type { paths as CorePaths } from '../../../api/generated/core';
import { createGatewayClient } from '../../../api/http';
import type { paths } from './generated';

/** The podcast feature's typed gateway client: the operations it uses and the kernel's (PA-2.4). */
export const api = createGatewayClient<CorePaths & paths>();
