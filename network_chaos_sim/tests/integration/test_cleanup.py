"""Teardown cleanup - no residual host network state.

WARNING: This test tears down the simulator. Run it last.

Verifies that ./launch.py down leaves no veth pairs, networks,
or drone containers on the host.
"""

import os
import subprocess
import time


SCRIPT_DIR = os.path.join(os.path.dirname(__file__), "..", "..")


def test_teardown_leaves_no_residual_state():
    """After teardown, no veth-d* interfaces, manet_mesh network, or drone containers remain."""
    # Tear down the simulator
    subprocess.run(
        [os.path.join(SCRIPT_DIR, "launch.py"), "down"],
        check=True, capture_output=True, text=True, timeout=60,
    )
    time.sleep(5)

    # No residual veth-d* interfaces
    links = subprocess.run(
        ["ip", "link", "show"], capture_output=True, text=True,
    )
    veth_count = links.stdout.count("veth-d")
    assert veth_count == 0, (
        f"Found {veth_count} residual veth-d* interfaces"
    )

    # manet_mesh network removed
    net_inspect = subprocess.run(
        ["docker", "network", "inspect", "manet_mesh"],
        capture_output=True, text=True,
    )
    assert net_inspect.returncode != 0, "manet_mesh network still exists"

    # No drone containers running
    ps = subprocess.run(
        ["docker", "ps", "-q", "--filter", "name=drone"],
        capture_output=True, text=True,
    )
    containers = ps.stdout.strip()
    assert containers == "", (
        f"Drone containers still running: {containers}"
    )
