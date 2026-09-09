#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TOOLS_ROOT="$REPO_ROOT/.tools"
NODE_VERSION="${OMNIX_AGENT_TOOLS_NODE_VERSION:-24.20.0}"
AGENT_BROWSER_VERSION="${OMNIX_AGENT_BROWSER_VERSION:-0.36.0}"
# Keep this below the worker npm registry's three-day release-age window.
MCPORTER_VERSION="${OMNIX_AGENT_MCPORTER_VERSION:-0.13.8}"
NODE_ROOT="$TOOLS_ROOT/node-v${NODE_VERSION}-linux-x64"
NODE_BIN="$NODE_ROOT/bin/node"
NPM_BIN="$NODE_ROOT/bin/npm"
NPM_PREFIX="$TOOLS_ROOT/npm-global"
AGENT_BROWSER_BIN="$NPM_PREFIX/bin/agent-browser"
MCPORTER_BIN="$NPM_PREFIX/bin/mcporter"

mkdir -p "$TOOLS_ROOT"

system_node="$(command -v node || true)"
use_system_node=0
if [ -n "$system_node" ]; then
  system_major="$(node --version | sed -E 's/^v([0-9]+).*/\1/')"
  if [ "${system_major:-0}" -ge 24 ]; then
    NODE_BIN="$system_node"
    NPM_BIN="$(dirname "$system_node")/npm"
    use_system_node=1
  fi
fi

if [ "$use_system_node" -eq 0 ] && [ ! -x "$NODE_BIN" ]; then
  archive="$TOOLS_ROOT/node-v${NODE_VERSION}-linux-x64.tar.xz"
  url="https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz"
  echo "Downloading Node.js $NODE_VERSION to the repository tool cache."
  curl --fail --location --silent --show-error "$url" --output "$archive"
  tar -xJf "$archive" -C "$TOOLS_ROOT"
fi

if [ ! -x "$NODE_BIN" ] || [ ! -x "$NPM_BIN" ]; then
  echo "Node.js $NODE_VERSION runtime was not installed correctly." >&2
  exit 1
fi

export PATH="$(dirname "$NODE_BIN"):$NPM_PREFIX/bin:$PATH"
echo "Installing agent-browser@$AGENT_BROWSER_VERSION and mcporter@$MCPORTER_VERSION."
"$NPM_BIN" install --global --prefix "$NPM_PREFIX" --no-fund --no-audit \
  "agent-browser@$AGENT_BROWSER_VERSION" "mcporter@$MCPORTER_VERSION"

if [ ! -x "$AGENT_BROWSER_BIN" ] || [ ! -x "$MCPORTER_BIN" ]; then
  echo "The Omnix agent tool command shims were not created under $NPM_PREFIX." >&2
  exit 1
fi

echo "Installing the agent-browser browser payload."
"$AGENT_BROWSER_BIN" install

cat <<EOF
Installed agent-browser: $AGENT_BROWSER_BIN
Installed MCPorter: $MCPORTER_BIN
Node runtime: $($NODE_BIN --version)

For direct shells, export:
  OMNIX_AGENT_BROWSER_COMMAND=$AGENT_BROWSER_BIN
  OMNIX_AGENT_MCPORTER_COMMAND=$MCPORTER_BIN
EOF
