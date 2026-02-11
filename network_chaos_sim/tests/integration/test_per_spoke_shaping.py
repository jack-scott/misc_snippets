"""Per-spoke shaping isolation.

Verifies that shaping applied to one drone's link does not affect
other drones' links.
"""

import time

from conftest import ping, set_link

SHAPED_MIN_LOSS = 5
UNSHAPED_MAX_LOSS = 0


def test_shaping_isolated_to_target_drone():
    """Shaping drone1 degrades drone1's link but not drone2->drone3."""
    set_link(1, delay_ms=50, loss_pct=20, rate_kbit=1000)
    time.sleep(2)

    # drone1 -> drone2: shaped, expect elevated loss
    shaped_loss, _ = ping("drone1_app", "172.31.0.12", count=30)
    assert shaped_loss >= SHAPED_MIN_LOSS, (
        f"Shaped link loss {shaped_loss}% below minimum {SHAPED_MIN_LOSS}%"
    )

    # drone2 -> drone3: unaffected, expect zero loss
    clean_loss, _ = ping("drone2_app", "172.31.0.13", count=20)
    assert clean_loss <= UNSHAPED_MAX_LOSS, (
        f"Unshaped link loss {clean_loss}% exceeds threshold {UNSHAPED_MAX_LOSS}%"
    )
