#!/bin/bash
# Omnix launcher (POSIX). A thin wrapper: `python -m app.launcher start` checks
# PostgreSQL, applies migrations, serves the launcher dashboard on
# http://127.0.0.1:5055 and starts the gateway and web app (WP-11.4).
# Interpreters: RPG_FLUX_PYTHON / RPG_TTS_PYTHON / RPG_STT_PYTHON, else
# resources/config/launcher.toml, else the Conda environments under CONDA_ROOT.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CONDA_ROOT="${CONDA_ROOT:-$HOME/miniconda3}"
RPG_FLUX_PYTHON="${RPG_FLUX_PYTHON:-$CONDA_ROOT/envs/${RPG_FLUX_ENV:-rpg-flux}/bin/python}"
if [ ! -x "$RPG_FLUX_PYTHON" ]; then
    echo "ERROR: the app runtime is missing: $RPG_FLUX_PYTHON. Run ./setup.sh first." >&2
    exit 1
fi
# The launcher starts the gateway with the same interpreter.
export RPG_FLUX_PYTHON

export PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
# Every child entrypoint validates public binding against OMNIX_ALLOW_LAN.
export OMNIX_BIND_HOST="${OMNIX_BIND_HOST:-127.0.0.1}"
for tool in agent-browser mcporter; do
    if [ -x "$SCRIPT_DIR/.tools/npm-global/bin/$tool" ]; then
        export PATH="$SCRIPT_DIR/.tools/npm-global/bin:$PATH"
    fi
done
if [ -x "$SCRIPT_DIR/.tools/npm-global/bin/agent-browser" ]; then
    export OMNIX_AGENT_BROWSER_COMMAND="$SCRIPT_DIR/.tools/npm-global/bin/agent-browser"
fi
if [ -x "$SCRIPT_DIR/.tools/npm-global/bin/mcporter" ]; then
    export OMNIX_AGENT_MCPORTER_COMMAND="$SCRIPT_DIR/.tools/npm-global/bin/mcporter"
fi

exec "$RPG_FLUX_PYTHON" -m app.launcher start "$@"
