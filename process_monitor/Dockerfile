# ── Build stage ──────────────────────────────────────────────────────────────
FROM ghcr.io/prefix-dev/pixi:0.62.1 AS base

FROM base AS source

WORKDIR /workspace

COPY . .

FROM source AS source_build
# Clean rattler cache in the same layer so it doesn't inflate the image
RUN --mount=type=cache,target=~/.cache/rattler pixi install
COPY src/cadvisor_monitor ros2_ws/src/cadvisor_monitor
# Generate a self-contained activation entrypoint (no pixi binary needed at runtime)
RUN echo '#!/bin/bash' > /workspace//entrypoint.sh && \
    pixi shell-hook -s bash >> /workspace//entrypoint.sh && \
    echo 'exec "$@"' >> /workspace//entrypoint.sh

FROM source AS prod_build
RUN --mount=type=cache,target=~/.cache/rattler pixi install -e prod
# Generate a self-contained activation entrypoint (no pixi binary needed at runtime)
RUN echo '#!/bin/bash' > /workspace//entrypoint.sh && \
    pixi shell-hook -s bash >> /workspace//entrypoint.sh && \
    echo 'exec "$@"' >> /workspace//entrypoint.sh


# ── CI stage ─────────────────────────────────────────────────────────────────
FROM ubuntu:24.04 AS prod

WORKDIR /workspace
# Pixi env (contains colcon, ROS, pytest, etc.) — no pixi binary
COPY --from=prod_build /workspace/.pixi/envs/prod /workspace/.pixi/envs/prod
# Built ROS workspace (src + install + build dirs for colcon test)
COPY --from=prod_build --chmod=0755 /workspace//entrypoint.sh /workspace//entrypoint.sh

ENTRYPOINT ["/workspace//entrypoint.sh"]

FROM ubuntu:24.04 AS dev

WORKDIR /workspace
# Pixi env (contains colcon, ROS, pytest, etc.) — no pixi binary
COPY --from=source_build /workspace/.pixi/envs/default /workspace/.pixi/envs/default

COPY --from=source_build /workspace/ros2_ws /workspace/ros2_ws
COPY --from=source_build --chmod=0755 /workspace//entrypoint.sh /workspace//entrypoint.sh

ENTRYPOINT ["/workspace//entrypoint.sh"]
