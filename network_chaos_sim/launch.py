#!/usr/bin/env python3
"""
MANET Chaos Simulator Launcher

Launches N drones with configurable network chaos simulation.

Usage:
    ./launch.py 3           # Launch 3 drones
    ./launch.py 5 --star    # Launch 5 drones + base station (star topology)
    ./launch.py down        # Stop everything
"""

import subprocess
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def run(cmd, check=True):
    """Run a shell command."""
    print(f"  $ {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=SCRIPT_DIR)
    if check and result.returncode != 0:
        print(f"Command failed with code {result.returncode}")
        sys.exit(1)
    return result.returncode == 0


def get_container_pid(container_name):
    """Get the PID of a running container's init process."""
    result = subprocess.run(
        f"docker inspect --format '{{{{.State.Pid}}}}' {container_name}",
        shell=True, capture_output=True, text=True, cwd=SCRIPT_DIR
    )
    if result.returncode != 0:
        return None
    pid = result.stdout.strip()
    if pid and pid != "0":
        return int(pid)
    return None


def setup_veth_pairs(drone_count):
    """Create veth pairs connecting app containers directly to radio containers.

    This bypasses Docker bridge networking (and br_netfilter) for routed
    inter-drone traffic. See design_doc.md section 2.2 for why this is needed.

    Addressing: 10.100.{drone_id}.1/30 (app) <-> 10.100.{drone_id}.2/30 (radio)
    """
    # Collect PIDs for all drones first
    drones = []
    for i in range(1, drone_count + 1):
        app_pid = get_container_pid(f"drone{i}_app")
        radio_pid = get_container_pid(f"drone{i}_radio")
        if not app_pid or not radio_pid:
            print(f"  Warning: Could not find PIDs for drone {i} (app={app_pid}, radio={radio_pid})")
            continue
        drones.append((i, app_pid, radio_pid))

    if not drones:
        print("  No drones to configure")
        return

    # Build a single script that creates all veth pairs and moves them into
    # the correct namespaces. Runs in one privileged container to avoid
    # pulling/installing iproute2 per drone.
    ip_cmds = []
    for i, app_pid, radio_pid in drones:
        veth_app = f"veth-d{i}-app"
        veth_radio = f"veth-d{i}-radio"
        ip_cmds.extend([
            f"ip link add {veth_app} type veth peer name {veth_radio}",
            f"ip link set {veth_app} netns {app_pid}",
            f"ip link set {veth_radio} netns {radio_pid}",
        ])

    script = " && ".join(ip_cmds)
    run(
        f"docker run --rm --privileged --net=host --pid=host alpine "
        f"sh -c 'apk add --no-cache -q iproute2 && {script}'",
        check=True,
    )

    # Configure addressing and routing inside each container via docker exec
    for i, _, _ in drones:
        app_name = f"drone{i}_app"
        radio_name = f"drone{i}_radio"
        veth_app = f"veth-d{i}-app"
        veth_radio = f"veth-d{i}-radio"

        # Configure app side
        for cmd in [
            f"ip addr add 10.100.{i}.1/30 dev {veth_app}",
            f"ip link set {veth_app} up",
            f"ip route add 172.31.0.0/24 via 10.100.{i}.2",
        ]:
            run(f"docker exec {app_name} {cmd}")

        # Configure radio side
        for cmd in [
            f"ip addr add 10.100.{i}.2/30 dev {veth_radio}",
            f"ip link set {veth_radio} up",
        ]:
            run(f"docker exec {radio_name} {cmd}")

        print(f"  Veth pair configured for drone {i}: "
              f"10.100.{i}.1 (app) <-> 10.100.{i}.2 (radio)")


def launch(drone_count, with_base_station=False):
    """Launch the MANET simulator with N drones."""
    print(f"\n=== Launching MANET Chaos Simulator ===")
    print(f"    Drones: {drone_count}")
    print(f"    Base Station: {'Yes' if with_base_station else 'No'}")
    print()

    # Create shared MANET mesh network
    print("Creating shared networks...")
    run("docker network create --subnet=172.31.0.0/24 manet_mesh 2>/dev/null || true", check=False)

    # Create shared metrics volume
    print("Creating shared volumes...")
    run("docker volume create manet_metrics 2>/dev/null || true", check=False)

    # Launch control plane (UI)
    print("\nStarting control plane...")
    run(f"DRONE_COUNT={drone_count} docker compose up -d --build")

    # Launch base station if requested
    if with_base_station:
        print("\n--- Base Station ---")
        run(f"DRONE_COUNT={drone_count} docker compose -f base_station/compose.yml -p base_station up -d --build")

    # Launch each drone
    print(f"\nStarting {drone_count} drones...")
    for i in range(1, drone_count + 1):
        print(f"\n--- Drone {i} ---")
        env = f"DRONE_ID={i} DRONE_COUNT={drone_count}"
        compose_files = "-f drone/compose.radio.yml -f drone/compose.app.yml"
        run(f"{env} docker compose {compose_files} -p drone{i} up -d --build")

    # Create veth pairs connecting app containers directly to radio containers.
    # This bypasses Docker bridge networking (and br_netfilter) for routed
    # inter-drone traffic. See design_doc.md section 2.2.
    print("\nSetting up veth pairs...")
    setup_veth_pairs(drone_count)

    print(f"\n{'='*50}")
    print(f"  MANET Simulator Ready")
    print(f"{'='*50}")
    print(f"  UI:           http://localhost:8080")
    print(f"  Drones:       {drone_count}")
    if with_base_station:
        print(f"  Base Station: Yes (172.31.0.10)")
    print(f"  Config:       config.yaml")
    print()
    print("Commands:")
    print("  docker logs -f drone1_radio   # View drone logs")
    print("  ./launch.py down              # Stop everything")
    print()


def stop():
    """Stop all containers."""
    print("\n=== Stopping MANET Chaos Simulator ===\n")

    # Find and stop all drone projects
    result = subprocess.run(
        "docker compose ls -q",
        shell=True, capture_output=True, text=True, cwd=SCRIPT_DIR
    )
    projects = result.stdout.strip().split("\n")

    for project in projects:
        if project.startswith("drone") or project == "base_station":
            print(f"Stopping {project}...")
            run(f"docker compose -p {project} down", check=False)

    # Stop control plane
    print("Stopping control plane...")
    run("docker compose down", check=False)

    # Remove shared resources
    print("Removing shared network...")
    run("docker network rm manet_mesh 2>/dev/null || true", check=False)

    print("\n=== Stopped ===")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    arg = sys.argv[1]

    if arg == "down" or arg == "stop":
        stop()
    elif arg.isdigit():
        drone_count = int(arg)
        if drone_count < 2:
            print("Need at least 2 drones for a network")
            sys.exit(1)
        if drone_count > 10:
            print("Warning: More than 10 drones may be slow")

        with_base_station = "--star" in sys.argv
        launch(drone_count, with_base_station)
    else:
        print(f"Unknown argument: {arg}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
