#!/usr/bin/env python3
"""
MANET Chaos Simulator — Generic Multi-Node Launcher

Brings up N radio nodes plus an optional experiment overlay.
Manages shared Docker resources (network, volumes) and component ordering.

Usage:
  ./launch.py up <N> [EXPERIMENT_COMPOSE] [options]
  ./launch.py down

Arguments:
  N                    Number of drone nodes (1-9)
  EXPERIMENT_COMPOSE   Path to experiment compose overlay (optional)
                       e.g. experiments/drone_fc/compose.yml

Options:
  --star         Add a base station node (DRONE_ID=0) for star topology
  --no-ui        Skip the web UI (control plane still starts)
  --no-rebuild   Don't rebuild images (use cached)

Examples:
  ./launch.py up 3
  ./launch.py up 3 experiments/drone_fc/compose.yml
  ./launch.py up 5 experiments/drone_fc/compose.yml --star
  ./launch.py up 3 experiments/my_algo/compose.yml --no-ui
  ./launch.py down
"""

import os
import re
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

RADIO_COMPOSE    = "radio/compose.yml"
CONTROL_COMPOSE  = "control_plane/compose.yml"
UI_COMPOSE       = "ui/compose.yml"

PROJECT_CONTROL  = "manet_control"
PROJECT_UI       = "manet_ui"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(cmd, check=True, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=SCRIPT_DIR, env=env)
    if check and result.returncode != 0:
        print(f"  Command failed (exit {result.returncode})")
        sys.exit(1)
    return result.returncode == 0


def compose_up(compose_files, project, env, rebuild=True, detach=True):
    files = " ".join(f"-f {f}" for f in compose_files)
    rebuild_flag = "--build" if rebuild else ""
    detach_flag  = "-d" if detach else ""
    env_str = " ".join(f"{k}={v}" for k, v in env.items())
    run(f"{env_str} docker compose {files} -p {project} up {rebuild_flag} {detach_flag}", env_extra=env)


def compose_down(project):
    run(f"docker compose -p {project} down", check=False)


def read_topology_default():
    config_path = os.path.join(SCRIPT_DIR, "config.yaml")
    if not os.path.exists(config_path):
        return "mesh"
    with open(config_path) as f:
        content = f.read()
    try:
        import yaml
        cfg = yaml.safe_load(content) or {}
        return cfg.get("topology", {}).get("default", "mesh")
    except ImportError:
        match = re.search(r"^topology:\s*\n\s+default:\s*(\S+)", content, re.MULTILINE)
        return match.group(1) if match else "mesh"


def running_projects():
    result = subprocess.run(
        "docker compose ls --format json",
        shell=True, capture_output=True, text=True, cwd=SCRIPT_DIR
    )
    if result.returncode != 0:
        # Fallback: plain text output
        result = subprocess.run(
            "docker compose ls -q",
            shell=True, capture_output=True, text=True, cwd=SCRIPT_DIR
        )
        return [p.strip() for p in result.stdout.strip().splitlines() if p.strip()]
    try:
        import json
        entries = json.loads(result.stdout) or []
        return [e["Name"] for e in entries if isinstance(e, dict)]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Up
# ---------------------------------------------------------------------------

def up(drone_count, experiment_compose=None, star=False, with_ui=True, rebuild=True):
    print(f"\n=== MANET Chaos Simulator — bringing up ===")
    print(f"  Drones:          {drone_count}")
    print(f"  Base station:    {'yes (star topology)' if star else 'no (mesh)'}")
    print(f"  Experiment:      {experiment_compose or '(radio only)'}")
    print(f"  UI:              {'yes' if with_ui else 'no'}")
    print()

    env_common = {
        "DRONE_COUNT": str(drone_count),
    }

    # Shared Docker resources — must exist before any compose stack starts
    print("Creating shared network and volumes...")
    run("docker network create --subnet=172.31.0.0/24 manet_mesh 2>/dev/null || true", check=False)
    run("docker volume create manet_metrics 2>/dev/null || true", check=False)

    # Control plane (creates manet_control network + manet_recordings volume)
    print("\nStarting control plane...")
    compose_up([CONTROL_COMPOSE], PROJECT_CONTROL, env_common, rebuild=rebuild)

    # UI (optional)
    if with_ui:
        print("\nStarting UI...")
        compose_up([UI_COMPOSE], PROJECT_UI, env_common, rebuild=rebuild)

    # Base station (DRONE_ID=0) — radio only, no experiment overlay
    if star:
        print("\nStarting base station (DRONE_ID=0)...")
        compose_up([RADIO_COMPOSE], "drone0", {**env_common, "DRONE_ID": "0"}, rebuild=rebuild)

    # Drone nodes
    compose_files = [RADIO_COMPOSE]
    if experiment_compose:
        compose_files.append(experiment_compose)

    print(f"\nStarting {drone_count} drone nodes...")
    for i in range(1, drone_count + 1):
        print(f"\n  --- drone {i} ---")
        compose_up(compose_files, f"drone{i}", {**env_common, "DRONE_ID": str(i)}, rebuild=rebuild)

    # Summary
    print(f"\n{'=' * 52}")
    print("  MANET Simulator ready")
    print(f"{'=' * 52}")
    if with_ui:
        print("  UI:              http://localhost:8080")
    print("  Foxglove:        ws://localhost:8765")
    print("  Log ingest:      http://localhost:9090/log")
    print(f"  Drones:          {drone_count}")
    if star:
        print("  Base station:    172.31.0.10 (drone0_radio)")
    if experiment_compose:
        print(f"  Experiment:      {experiment_compose}")
    print()
    print("Useful commands:")
    print("  docker logs -f drone1_radio     # radio sidecar logs")
    print("  docker logs -f manet_foxglove   # logger logs")
    print("  ./launch.py down                # stop everything")
    print()


# ---------------------------------------------------------------------------
# Down
# ---------------------------------------------------------------------------

def down():
    print("\n=== MANET Chaos Simulator — tearing down ===\n")

    projects = running_projects()

    # Stop drone and base station projects first
    drone_projects = sorted(
        [p for p in projects if re.match(r"drone\d+$", p)],
        key=lambda p: int(p[5:]),
        reverse=True,
    )
    for project in drone_projects:
        print(f"Stopping {project}...")
        compose_down(project)

    # Stop UI and control plane
    for project in (PROJECT_UI, PROJECT_CONTROL):
        if project in projects:
            print(f"Stopping {project}...")
        compose_down(project)

    # Remove shared network (volumes are intentionally kept for post-mortem inspection)
    print("\nRemoving shared network...")
    run("docker network rm manet_mesh 2>/dev/null || true", check=False)

    print("\n=== Done ===")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    cmd = args[0]

    if cmd == "down":
        down()
        return

    if cmd != "up":
        # Legacy: treat a bare number as "up N" for backwards compatibility
        if cmd.isdigit():
            args = ["up"] + args
            cmd = "up"
        else:
            print(f"Unknown command: {cmd}")
            print(__doc__)
            sys.exit(1)

    # Parse "up" arguments
    positional = [a for a in args[1:] if not a.startswith("--")]
    flags      = [a for a in args[1:] if a.startswith("--")]

    if not positional:
        print("Error: drone count required.\n")
        print(__doc__)
        sys.exit(1)

    if not positional[0].isdigit():
        print(f"Error: expected drone count, got '{positional[0]}'")
        sys.exit(1)

    drone_count = int(positional[0])

    if drone_count < 1:
        print("Error: need at least 1 drone")
        sys.exit(1)
    if drone_count > 9:
        print(f"Warning: {drone_count} drones — IP scheme supports max 9 (IDs 1-9)")

    experiment_compose = positional[1] if len(positional) > 1 else None

    if experiment_compose and not os.path.exists(os.path.join(SCRIPT_DIR, experiment_compose)):
        print(f"Error: experiment compose not found: {experiment_compose}")
        sys.exit(1)

    star = "--star" in flags
    with_ui = "--no-ui" not in flags
    rebuild = "--no-rebuild" not in flags

    if not star:
        topology_default = read_topology_default()
        if topology_default == "star":
            print("Note: config.yaml has topology.default=star — adding base station (--star)")
            star = True

    up(drone_count, experiment_compose, star=star, with_ui=with_ui, rebuild=rebuild)


if __name__ == "__main__":
    main()
