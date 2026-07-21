#!/usr/bin/env bash
set -euo pipefail

# Bakes cadvisor_monitor's diagnostics label into its image from the config
# it ships (src/cadvisor_monitor/config/analyzers.yaml), via `contents
# encode` (../contents) — see compose.yaml's build.args and the Dockerfile's
# ARG CADVISOR_MONITOR_DIAGNOSTICS / LABEL.

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(dirname "$script_dir")"
diag_file="$project_dir/src/cadvisor_monitor/config/analyzers.yaml"

export $(contents encode --pkg cadvisor_monitor --field diagnostics $diag_file)

exec  docker compose -f $project_dir/compose.build.yaml build prod "$@"
