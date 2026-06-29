#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${OMNIX_ENV_FILE:-$ROOT_DIR/.env.local}"
HERMES_BASE_URL_VALUE="${HERMES_BASE_URL:-http://127.0.0.1:8642}"
HERMES_TIMEOUT_SECONDS_VALUE="${HERMES_TIMEOUT_SECONDS:-45}"
SKIP_INSTALL_VALUE="${OMNIX_HERMES_SKIP_INSTALL:-0}"

append_env_if_missing() {
  local key="$1"
  local value="$2"
  touch "$ENV_FILE"
  if ! grep -q "^${key}=" "$ENV_FILE"; then
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

echo "Preparing optional Hermes Agent sidecar setup."
echo "Env file: $ENV_FILE"

if [[ "$SKIP_INSTALL_VALUE" != "1" ]]; then
  echo "Running the official Hermes Agent installer."
  curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
else
  echo "Skipping Hermes install because OMNIX_HERMES_SKIP_INSTALL=1."
fi

append_env_if_missing "HERMES_ENABLED" "false"
append_env_if_missing "HERMES_BASE_URL" "$HERMES_BASE_URL_VALUE"
append_env_if_missing "HERMES_TIMEOUT_SECONDS" "$HERMES_TIMEOUT_SECONDS_VALUE"

echo "Hermes sidecar env defaults written. Set HERMES_ENABLED=true after starting Hermes."
