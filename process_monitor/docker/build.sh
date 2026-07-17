#!/usr/bin/env bash
set -euo pipefail

# Bakes cadvisor_monitor's diagnostics.analyzers label into its image from
# the config it ships (src/cadvisor_monitor/config/analyzers.yaml) — see
# compose.yaml's build.args and the Dockerfile's ARG DIAGNOSTICS_ANALYZERS /
# LABEL. Flattened here to single-line flow-style YAML (semantically
# identical to the block-style source) so the value can't be corrupted by a
# shell or tool collapsing embedded newlines along the way.

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(dirname "$script_dir")"
config_file="$project_dir/src/cadvisor_monitor/config/analyzers.yaml"

export DIAGNOSTICS_ANALYZERS
DIAGNOSTICS_ANALYZERS="$(python3 -c "
import yaml
with open('$config_file') as f:
    fragment = yaml.safe_load(f)
print(yaml.safe_dump(fragment, default_flow_style=True, width=float('inf')).strip())
")"

exec docker compose -f "$project_dir/compose.yaml" build cadvisor_monitor "$@"
