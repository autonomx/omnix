# Agent sandbox image (WP-4.7): the Pi coding agent and a basic toolchain for
# sandboxed agent runs. Omnix runs it read-only, without capabilities, as a
# non-root user, on an internal network that reaches only the broker relay
# (see docs/security/AGENT_SANDBOX.md).
#
#   python -m app.agent_runtime.sandbox build
#
# Projects whose tests need more (a Python virtualenv, a database client)
# extend this image and point OMNIX_AGENT_DOCKER_IMAGE at theirs.
FROM node:22-bookworm-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c

ARG PI_VERSION=0.85.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global --no-fund --no-audit "@earendil-works/pi-coding-agent@${PI_VERSION}" \
    && npm cache clean --force \
    && git config --system safe.directory /workspace

# The root file system is read-only at run time; home lives on the /tmp tmpfs.
ENV HOME=/tmp/home \
    NPM_CONFIG_CACHE=/tmp/home/.npm \
    PYTHONDONTWRITEBYTECODE=1
USER node
WORKDIR /workspace
ENTRYPOINT []
