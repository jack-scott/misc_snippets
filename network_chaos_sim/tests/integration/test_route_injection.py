"""Route injection - all app containers can reach reachable peers.

Verifies that veth pair setup by launch.py correctly routes traffic from
every app container to every reachable drone (topology-dependent).
"""

import pytest

from conftest import get_reachable_pairs, ping

pytestmark = pytest.mark.usefixtures("reset_links")


def test_app_reaches_all_reachable_peers(simulator):
    """Every app container can ping every reachable peer with 0% loss."""
    expected_loss = 0
    pairs = get_reachable_pairs(simulator)
    failures = []

    for src, dst_ip in pairs:
        loss, _ = ping(f"drone{src}_app", dst_ip, count=3)
        if loss != expected_loss:
            failures.append(f"drone{src}_app -> {dst_ip}: {loss}% loss")

    assert not failures, (
        f"{len(failures)} route(s) failed:\n" + "\n".join(failures)
    )
