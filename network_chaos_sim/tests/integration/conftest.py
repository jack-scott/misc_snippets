"""Fixtures and helpers for integration tests.

Prerequisites: simulator must be running (./launch.py 3).
"""

import re
import subprocess
import time

import pytest
import requests

API_URL = "http://localhost:8080"
DRONE_COUNT = 3


def docker_exec(container, cmd, check=True):
    """Run a command inside a Docker container, return stdout."""
    result = subprocess.run(
        ["docker", "exec", container] + cmd,
        capture_output=True, text=True, timeout=30,
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
    result = docker_exec(
        container,
        ["ping", "-c", str(count), "-W", str(timeout), "-q", target],
        check=False,
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


@pytest.fixture(autouse=True)
def reset_links():
    """Reset all drone links to clean state before and after each test."""
    for i in range(1, DRONE_COUNT + 1):
        link_up(i)
    time.sleep(2)
    yield
    for i in range(1, DRONE_COUNT + 1):
        link_up(i)
