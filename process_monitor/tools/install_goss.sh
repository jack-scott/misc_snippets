#!/usr/bin/env bash
# Downloads pinned goss/dgoss binaries into ci/bin/ with checksum verification.
# Run via `pixi run install-goss`; every other CI task depends on this one
# instead of assuming goss/dgoss are present on the host or image.
set -euo pipefail

GOSS_VERSION="0.4.9"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${SCRIPT_DIR}/../ci/bin"
BASE_URL="https://github.com/goss-org/goss/releases/download/v${GOSS_VERSION}"

case "$(uname -m)" in
    x86_64) GOSS_ARCH="amd64" ;;
    aarch64|arm64) GOSS_ARCH="arm64" ;;
    *) echo "install_goss.sh: unsupported architecture $(uname -m)" >&2; exit 1 ;;
esac

# name -> expected sha256 (pinned from the v0.4.9 release .sha256 assets)
declare -A CHECKSUMS=(
    ["goss-linux-amd64"]="87dd36cfa1b8b50554e6e2ca29168272e26755b19ba5438341f7c66b36decc19"
    ["goss-linux-arm64"]="14fd24ac08236559f4809e6a627792d1b947ed98654bba1662ef1d6122d77e18"
    ["dgoss"]="7ee35d6ccbe1440eb2a08984a43e8b3742f2e849abdc0d7384ac08de55682d7c"
    ["dcgoss"]="e14e961dd6efd626d0d0d0a74914047c72913d4194495b561171516d3ed132d4"
)

mkdir -p "${BIN_DIR}"

fetch() {
    local asset="$1" dest="$2"
    local expected="${CHECKSUMS[${asset}]}"

    if [[ -f "${dest}" ]] && echo "${expected}  ${dest}" | sha256sum -c - >/dev/null 2>&1; then
        echo "install_goss.sh: ${asset} already present and verified, skipping download"
        return
    fi

    echo "install_goss.sh: fetching ${asset} (goss v${GOSS_VERSION})"
    curl -sL --fail -o "${dest}" "${BASE_URL}/${asset}"

    if ! echo "${expected}  ${dest}" | sha256sum -c -; then
        echo "install_goss.sh: checksum mismatch for ${asset}, aborting" >&2
        rm -f "${dest}"
        exit 1
    fi

    chmod +x "${dest}"
}

fetch "goss-linux-${GOSS_ARCH}" "${BIN_DIR}/goss"
fetch "dgoss" "${BIN_DIR}/dgoss"
fetch "dcgoss" "${BIN_DIR}/dcgoss"

# dcgoss shells out to the old standalone `docker-compose` binary; shim it to
# the `docker compose` v2 plugin so dcgoss works without the legacy binary installed
cp "${SCRIPT_DIR}/docker-compose-shim.sh" "${BIN_DIR}/docker-compose"
chmod +x "${BIN_DIR}/docker-compose"

echo "install_goss.sh: goss, dgoss, dcgoss and docker-compose shim ready in ${BIN_DIR}"
