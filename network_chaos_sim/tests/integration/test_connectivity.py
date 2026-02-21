"""Inter-drone connectivity via veth pairs and radio sidecar.

Verifies that app containers can reach other drones through the veth pair
routing set up by launch.py.  Runs in both mesh and star topologies.
"""

import pytest

from conftest import docker_exec, get_reachable_target, get_unreachable_target, ping

pytestmark = pytest.mark.usefixtures("reset_links")


def test_veth_route_exists(simulator):
    """Route to 172.31.0.0/24 via veth gateway must be present."""
    result = docker_exec("drone1_app", ["ip", "route", "show", "172.31.0.0/24"])
    assert "10.100.1.2" in result.stdout, (
        f"Expected route via 10.100.1.2, got: {result.stdout}"
    )


def test_veth_interface_exists(simulator):
    """veth-d1-app interface must exist in the app container."""
    result = docker_exec(
        "drone1_app", ["ip", "link", "show", "veth-d1-app"], check=False,
    )
    assert result.returncode == 0, "veth-d1-app interface not found in drone1_app"


def test_drone1_pings_reachable_target(simulator):
    """drone1 app can ping a reachable peer with 0% loss."""
    expected_loss = 0
    target = get_reachable_target(simulator, 1)
    loss, _ = ping("drone1_app", target, count=5)
    assert loss == expected_loss, f"Expected {expected_loss}% loss to {target}, got {loss}%"


def test_drone2_pings_reachable_target(simulator):
    """drone2 app can ping a reachable peer with 0% loss."""
    expected_loss = 0
    target = get_reachable_target(simulator, 2)
    loss, _ = ping("drone2_app", target, count=5)
    assert loss == expected_loss, f"Expected {expected_loss}% loss to {target}, got {loss}%"


def test_star_base_station_not_directly_reachable(simulator):
    """In star mode, the base station IP is not directly addressable."""
    target = get_unreachable_target(simulator, 1)
    if target is None:
        pytest.skip("No unreachable targets in mesh topology")

    expected_loss = 100
    loss, _ = ping("drone1_app", target, count=5)
    assert loss == expected_loss, (
        f"Base station should be invisible: expected {expected_loss}% loss "
        f"to {target}, got {loss}%"
    )
