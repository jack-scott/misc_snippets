#!/usr/bin/env bash
set -euo pipefail

# Bakes cadvisor_monitor's diagnostics label into its image from the config
# it ships (src/cadvisor_monitor/config/analyzers.yaml), via `contents
# encode` (../contents) — see compose.yaml's build.args and the Dockerfile's
# ARG CADVISOR_MONITOR_DIAGNOSTICS / LABEL.

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(dirname "$script_dir")"
contents_manifest="$(dirname "$project_dir")/contents/pixi.toml"
config_file="$project_dir/src/cadvisor_monitor/config/analyzers.yaml"

# TODO: once contents is published to jacks-channel and added as a
# dependency of this project, replace this with a plain `contents encode
# ...` call.
export CADVISOR_MONITOR_DIAGNOSTICS
CADVISOR_MONITOR_DIAGNOSTICS="$(
    pixi run --manifest-path "$contents_manifest" contents encode --pkg cadvisor_monitor --field diagnostics "$config_file" \
        | cut -d= -f2-
)"

exec docker compose -f "$project_dir/compose.yaml" build cadvisor_monitor "$@"
