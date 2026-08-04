#!/bin/bash
set -euo pipefail

MOSHI_VERSION="${KYUTAI_MOSHI_SERVER_VERSION:-0.6.4}"
INSTALL_ROOT="${KYUTAI_MOSHI_INSTALL_ROOT:-/app/omnix-cargo-install}"
BINARY_PATH="${INSTALL_ROOT}/bin/moshi-server"
STAMP_PATH="${INSTALL_ROOT}/.omnix-moshi-version"
BUILD_NICE_LEVEL="${OMNIX_KYUTAI_BUILD_NICE_LEVEL:-10}"

export LD_LIBRARY_PATH="$(python3 -c 'import sysconfig; print(sysconfig.get_config_var("LIBDIR"))')"
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-/app/target}"
export CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-2}"
export CMAKE_BUILD_PARALLEL_LEVEL="${CMAKE_BUILD_PARALLEL_LEVEL:-2}"
export UV_CONCURRENT_BUILDS="${UV_CONCURRENT_BUILDS:-1}"
export UV_CONCURRENT_INSTALLS="${UV_CONCURRENT_INSTALLS:-2}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"

mkdir -p "${INSTALL_ROOT}"

if [[ -n "${HUGGING_FACE_HUB_TOKEN:-}" ]]; then
  # Preserve upstream authentication behavior without shell tracing or token output.
  uvx hf auth login --token "${HUGGING_FACE_HUB_TOKEN}" >/dev/null 2>&1
  echo "[KYUTAI MOSHI] Hugging Face authentication completed."
else
  echo "[KYUTAI MOSHI] WARNING: Hugging Face token is not configured."
fi

installed_version=""
if [[ -f "${STAMP_PATH}" ]]; then
  installed_version="$(cat "${STAMP_PATH}" 2>/dev/null || true)"
fi

if [[ ! -x "${BINARY_PATH}" || "${installed_version}" != "${MOSHI_VERSION}" ]]; then
  echo "[KYUTAI MOSHI] Compiling moshi-server ${MOSHI_VERSION} with ${CARGO_BUILD_JOBS} Cargo job(s)."
  nice -n "${BUILD_NICE_LEVEL}" cargo install \
    --root "${INSTALL_ROOT}" \
    --features cuda \
    "moshi-server@${MOSHI_VERSION}"
  printf '%s' "${MOSHI_VERSION}" > "${STAMP_PATH}"
else
  echo "[KYUTAI MOSHI] Reusing cached moshi-server ${MOSHI_VERSION} binary."
fi

exec "${BINARY_PATH}" "$@"
