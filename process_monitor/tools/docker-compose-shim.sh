#!/usr/bin/env bash
# dcgoss hardcodes calls to the old standalone `docker-compose` binary.
# This host only has the `docker compose` v2 CLI plugin, so install_goss.sh
# drops this on PATH ahead of dcgoss as `docker-compose`.
exec docker compose -f docker-compose.yaml "$@"
