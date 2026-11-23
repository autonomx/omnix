import { ApiError, GatewayCallError } from '../api/errors';

/** The error a feature client throws when the gateway refuses a call with `status`. */
export function gatewayCallError(message: string, status = 409, detail = ''): GatewayCallError {
  return new GatewayCallError(message, new ApiError(status, JSON.stringify({ detail })));
}
