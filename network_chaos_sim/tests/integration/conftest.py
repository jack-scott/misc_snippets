"""Fixtures and helpers for integration tests.

The ``simulator`` fixture is session-scoped and parameterised over
["mesh", "star"].  Each parameter value launches the full stack
(``./launch.py 3``), runs every collected test, then tears it down.

Prerequisites: Docker must be running and the images must be buildable.
"""

import os
import re
import subprocess
import time

import pytest
import requests

API_URL = "http://localhost:8080"
DRONE_COUNT = 3
SCRIPT_DIR = os.path.join(os.path.dirname(__file__), "..", "..")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.yaml")


# ---------------------------------------------------------------------------
# Topology helpers
# ---------------------------------------------------------------------------

def get_drone_ip(drone_id):
    if drone_id == 0:
        return "172.31.0.10"
    return f"172.31.0.1{drone_id}"


def get_reachable_target(topology, drone_id):
    """Return a single reachable peer IP for *drone_id* under *topology*.

    In both topologies drones can reach other drones.  In star mode the
    base station is transparent infrastructure (like a switch) — traffic
    goes through it, but drones address each other directly.
    """
    target = (drone_id % DRONE_COUNT) + 1
    return get_drone_ip(target)


def get_reachable_pairs(topology):
    """Return list of (src_drone_id, dst_ip) pairs that should be reachable."""
    pairs = []
    for src in range(1, DRONE_COUNT + 1):
        for dst in range(1, DRONE_COUNT + 1):
            if dst != src:
                pairs.append((src, get_drone_ip(dst)))
    return pairs


def get_unreachable_target(topology, drone_id):
    """Return a peer IP that should be blocked under *topology*, or None.

    In star mode the base station IP is not directly reachable — it's
    invisible infrastructure.  In mesh mode there is no base station.
    """
    if topology == "star":
        return get_drone_ip(0)  # base station is invisible, not addressable
    return None


# ---------------------------------------------------------------------------
# Docker / network helpers
# ---------------------------------------------------------------------------

def docker_exec(container, cmd, check=True, timeout=30):
    """Run a command inside a Docker container, return stdout."""
    result = subprocess.run(
        ["docker", "exec", container] + cmd,
        capture_output=True, text=True, timeout=timeout,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"docker exec {container} {' '.join(cmd)} failed "
            f"(rc={result.returncode}): {result.stderr}"
        )
    return result


def ping(container, target, count=5, timeout=2):
    """Ping a target from inside a container. Returns (loss_pct, avg_rtt_ms).

    loss_pct: integer 0-100
    avg_rtt_ms: float, or None if 100% loss
    """
    exec_timeout = int(count * 0.5 + timeout + 10)
    result = docker_exec(
        container,
        ["ping", "-c", str(count), "-W", str(timeout), "-i", "0.5", "-q", target],
        check=False,
        timeout=exec_timeout,
    )
    output = result.stdout

    loss_match = re.search(r"(\d+)% packet loss", output)
    loss_pct = int(loss_match.group(1)) if loss_match else 100

    avg_rtt = None
    rtt_match = re.search(r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)/", output)
    if rtt_match:
        avg_rtt = float(rtt_match.group(1))

    return loss_pct, avg_rtt


def set_link(drone_id, delay_ms=0, loss_pct=0, rate_kbit=1000):
    """Set absolute link parameters for a drone."""
    requests.post(
        f"{API_URL}/drones/{drone_id}/link",
        json={"delay_ms": delay_ms, "loss_pct": loss_pct, "rate_kbit": rate_kbit},
        timeout=5,
    ).raise_for_status()


def link_up(drone_id):
    """Restore a drone's link to normal."""
    requests.post(f"{API_URL}/drones/{drone_id}/up", timeout=5).raise_for_status()


def link_down(drone_id):
    """Simulate a drone out of range (100% loss)."""
    requests.post(f"{API_URL}/drones/{drone_id}/down", timeout=5).raise_for_status()


# ---------------------------------------------------------------------------
# Config management
# ---------------------------------------------------------------------------

_original_config = None


def _write_topology_to_config(topology):
    """Overwrite the ``topology.default`` value in config.yaml."""
    global _original_config
    with open(CONFIG_PATH) as f:
        content = f.read()

    if _original_config is None:
        _original_config = content

    new_content = re.sub(
        r"(^  default:\s*)\S+",
        rf"\g<1>{topology}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    with open(CONFIG_PATH, "w") as f:
        f.write(new_content)


def _restore_config():
    global _original_config
    if _original_config is not None:
        with open(CONFIG_PATH, "w") as f:
            f.write(_original_config)
        _original_config = None


def _wait_for_ready(timeout=120):
    """Block until the control plane API is responsive."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{API_URL}/status", timeout=3)
            if r.status_code == 200:
                return
        except requests.ConnectionError:
            pass
        time.sleep(2)
    raise TimeoutError("Simulator did not become ready")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", params=["mesh", "star"])
def simulator(request):
    """Launch the simulator in the requested topology, yield the mode string,
    then tear it down."""
    topology = request.param

    _write_topology_to_config(topology)

    # Launch (launch.py reads config.yaml for topology)
    subprocess.run(
        ["python3", os.path.join(SCRIPT_DIR, "launch.py"), str(DRONE_COUNT)],
        check=True, capture_output=True, text=True, timeout=180,
        cwd=SCRIPT_DIR,
    )

    _wait_for_ready()
    # Let link rules settle
    time.sleep(5)

    yield topology

    # Teardown
    subprocess.run(
        ["python3", os.path.join(SCRIPT_DIR, "launch.py"), "down"],
        capture_output=True, text=True, timeout=60,
        cwd=SCRIPT_DIR,
    )
    time.sleep(5)
    _restore_config()


@pytest.fixture()
def reset_links(simulator):
    """Reset all drone links (and base station in star mode) before and after
    each test.  Test files opt in via ``pytestmark``."""
    ids_to_reset = list(range(1, DRONE_COUNT + 1))

    for i in ids_to_reset:
        try:
            link_up(i)
        except Exception:
            pass
    time.sleep(2)

    yield

    for i in ids_to_reset:
        try:
            link_up(i)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Collection hook — ensure test_cleanup always runs last
# ---------------------------------------------------------------------------

def pytest_collection_modifyitems(items):
    """Move any item whose module name contains 'test_cleanup' to the end."""
    cleanup = [i for i in items if "test_cleanup" in i.module.__name__]
    rest = [i for i in items if "test_cleanup" not in i.module.__name__]
    items[:] = rest + cleanup
