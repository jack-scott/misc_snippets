# ── Build stage ──────────────────────────────────────────────────────────────
FROM ghcr.io/prefix-dev/pixi:0.62.1 AS base

FROM base AS source

WORKDIR /workspace

COPY . .

FROM source AS source_build
# Clean rattler cache in the same layer so it doesn't inflate the image
RUN --mount=type=cache,target=~/.cache/rattler pixi install
# activate.sh: sourceable env setup (used by .bashrc for exec'd shells)
# entrypoint.sh: sources activate.sh then execs the command (used by docker run)
RUN pixi shell-hook -s bash > /workspace/activate.sh && \
    echo '#!/bin/bash' > /workspace/entrypoint.sh && \
    echo '. /workspace/activate.sh' >> /workspace/entrypoint.sh && \
    echo 'exec "$@"' >> /workspace/entrypoint.sh


COPY src/cadvisor_monitor /workspace/process_monitor/src/cadvisor_monitor
RUN mkdir -p /workspace/ros2_ws/src/
#setup folders so when we mount volumes here later they have the correct permissions
RUN cd /workspace/ros2_ws/ && pixi run colcon build
RUN ln -s /workspace/process_monitor/src/cadvisor_monitor /workspace/ros2_ws/src/


FROM source_build AS test
WORKDIR /workspace/ros2_ws
RUN pixi run colcon build
ENTRYPOINT ["/workspace/entrypoint.sh"]
CMD ["colcon", "test"]

FROM source AS prod_build
RUN --mount=type=cache,target=~/.cache/rattler pixi install -e prod
RUN pixi shell-hook -e prod -s bash > /workspace/activate.sh && \
    echo '#!/bin/bash' > /workspace/entrypoint.sh && \
    echo '. /workspace/activate.sh' >> /workspace/entrypoint.sh && \
    echo 'exec "$@"' >> /workspace/entrypoint.sh


# ── CI stage ─────────────────────────────────────────────────────────────────
FROM ubuntu:24.04 AS prod


WORKDIR /workspace
# Pixi env (contains colcon, ROS, pytest, etc.) — no pixi binary
COPY --from=prod_build /workspace/.pixi/envs/prod /workspace/.pixi/envs/prod
# Built ROS workspace (src + install + build dirs for colcon test)
COPY --from=prod_build --chmod=0755 /workspace/entrypoint.sh /workspace/entrypoint.sh
RUN chown -R ubuntu:ubuntu /workspace

USER ubuntu
ENTRYPOINT ["/workspace/entrypoint.sh"]

FROM ubuntu:24.04 AS dev


WORKDIR /workspace
# Pixi env (contains colcon, ROS, pytest, etc.) — no pixi binary
COPY --from=source_build /workspace/.pixi/envs/default /workspace/.pixi/envs/default
COPY --from=source_build /workspace/ros2_ws /workspace/ros2_ws
COPY --from=source_build /workspace/process_monitor /workspace/process_monitor
COPY --from=source_build /workspace/activate.sh /workspace/activate.sh
COPY --from=source_build --chmod=0755 /workspace/entrypoint.sh /workspace/entrypoint.sh
RUN chown -R ubuntu:ubuntu /workspace
# Source activate.sh for exec'd shells (docker exec bash, VS Code terminal, etc.)
RUN echo '. /workspace/activate.sh' >> /home/ubuntu/.bashrc

USER ubuntu
ENTRYPOINT ["/workspace/entrypoint.sh"]
