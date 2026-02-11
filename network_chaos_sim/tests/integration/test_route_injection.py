"""Route injection - all app containers can reach all other drones.

Verifies that veth pair setup by launch.py correctly routes traffic from
every app container to every other drone's radio.
"""

import pytest

from conftest import DRONE_COUNT, ping


def _all_pairs():
    """Generate all (src, dst) drone pairs."""
    for src in range(1, DRONE_COUNT + 1):
        for dst in range(1, DRONE_COUNT + 1):
            if src != dst:
                yield src, dst


@pytest.mark.parametrize("src,dst", list(_all_pairs()))
def test_app_reaches_drone(src, dst):
    """drone{src}_app can ping drone{dst}_radio."""
    expected_loss = 0
    loss, _ = ping(f"drone{src}_app", f"172.31.0.1{dst}", count=3)
    assert loss == expected_loss, (
        f"drone{src}_app -> 172.31.0.1{dst}: {loss}% loss"
    )
