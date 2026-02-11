"""Inter-drone connectivity via veth pairs and radio sidecar.

Verifies that app containers can reach other drones through the veth pair
routing set up by launch.py.
"""

from conftest import docker_exec, ping


def test_veth_route_exists():
    """Route to 172.31.0.0/24 via veth gateway must be present."""
    result = docker_exec("drone1_app", ["ip", "route", "show", "172.31.0.0/24"])
    assert "10.100.1.2" in result.stdout, (
        f"Expected route via 10.100.1.2, got: {result.stdout}"
    )


def test_veth_interface_exists():
    """veth-d1-app interface must exist in the app container."""
    result = docker_exec(
        "drone1_app", ["ip", "link", "show", "veth-d1-app"], check=False,
    )
    assert result.returncode == 0, "veth-d1-app interface not found in drone1_app"


def test_drone1_pings_drone2():
    """drone1 app can ping drone2 radio with 0% loss."""
    expected_loss = 0
    loss, _ = ping("drone1_app", "172.31.0.12", count=5)
    assert loss == expected_loss, f"Expected {expected_loss}% loss, got {loss}%"


def test_drone2_pings_drone1():
    """drone2 app can ping drone1 radio with 0% loss."""
    expected_loss = 0
    loss, _ = ping("drone2_app", "172.31.0.11", count=5)
    assert loss == expected_loss, f"Expected {expected_loss}% loss, got {loss}%"
