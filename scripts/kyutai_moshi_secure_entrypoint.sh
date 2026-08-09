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

args=("$@")
delay_tokens="${OMNIX_KYUTAI_ASR_DELAY_TOKENS:-}"
if [[ -n "${delay_tokens}" ]]; then
  if [[ ! "${delay_tokens}" =~ ^[1-9][0-9]*$ ]] || (( delay_tokens > 32 )); then
    echo "[KYUTAI MOSHI] ERROR: OMNIX_KYUTAI_ASR_DELAY_TOKENS must be an integer from 1 to 32." >&2
    exit 2
  fi

  config_path=""
  config_arg_index=-1
  for ((index = 0; index < ${#args[@]}; index++)); do
    if [[ "${args[$index]}" == "--config" && $((index + 1)) -lt ${#args[@]} ]]; then
      config_path="${args[$((index + 1))]}"
      config_arg_index=$((index + 1))
      break
    fi
  done

  if [[ -z "${config_path}" || ! -f "${config_path}" ]]; then
    echo "[KYUTAI MOSHI] ERROR: ASR delay override requested but the moshi-server config could not be resolved." >&2
    exit 2
  fi
  if ! grep -Eq '^[[:space:]]*asr_delay_in_tokens[[:space:]]*=' "${config_path}"; then
    echo "[KYUTAI MOSHI] ERROR: ASR delay override requested but asr_delay_in_tokens is absent from ${config_path}." >&2
    exit 2
  fi

  override_config="/tmp/omnix-stt-delay-${delay_tokens}.toml"
  cp "${config_path}" "${override_config}"
  sed -E -i \
    "s/^([[:space:]]*asr_delay_in_tokens[[:space:]]*=[[:space:]]*)[0-9]+/\\1${delay_tokens}/" \
    "${override_config}"
  args[$config_arg_index]="${override_config}"
  echo "[KYUTAI MOSHI] Experimental ASR delay override active: asr_delay_in_tokens=${delay_tokens}."
fi

exec "${BINARY_PATH}" "${args[@]}"