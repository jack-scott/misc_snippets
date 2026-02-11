"""Per-spoke shaping isolation.

Verifies that shaping applied to one drone's link does not affect
other drones' links.
"""

import time

import pytest

from conftest import get_drone_ip, get_reachable_target, ping, set_link

pytestmark = pytest.mark.usefixtures("reset_links")

SHAPED_MIN_LOSS = 5
UNSHAPED_MAX_LOSS = 0


def test_shaping_isolated_to_target_drone(simulator):
    """Shaping drone1 degrades drone1's link but not an unshaped path."""
    # Shaped target: a reachable peer for drone1
    shaped_target = get_reachable_target(simulator, 1)

    # Unshaped path: drone2 -> drone3 (not drone1, to avoid cross-contamination
    # from drone1's shaping).  Works in both topologies.
    unshaped_target = get_drone_ip(3)

    set_link(1, delay_ms=50, loss_pct=20, rate_kbit=1000)
    time.sleep(2)

    # drone1 -> shaped target: expect elevated loss
    shaped_loss, _ = ping("drone1_app", shaped_target, count=30)
    assert shaped_loss >= SHAPED_MIN_LOSS, (
        f"Shaped link loss {shaped_loss}% below minimum {SHAPED_MIN_LOSS}%"
    )

    # drone2 -> unshaped target: expect zero loss
    clean_loss, _ = ping("drone2_app", unshaped_target, count=20)
    assert clean_loss <= UNSHAPED_MAX_LOSS, (
        f"Unshaped link loss {clean_loss}% exceeds threshold {UNSHAPED_MAX_LOSS}%"
    )
