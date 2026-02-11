"""Dynamic link control via API.

Verifies that the controller API can set link parameters and that
ping results reflect the configured loss.
"""

import time

from conftest import link_down, link_up, ping, set_link


def test_clean_link_zero_loss():
    """0% configured loss produces 0% measured loss."""
    expected_loss = 0
    set_link(1, delay_ms=10, loss_pct=0, rate_kbit=1000)
    time.sleep(2)

    loss, _ = ping("drone1_app", "172.31.0.12", count=20)
    assert loss == expected_loss, f"Clean link showed {loss}% loss"


def test_full_loss():
    """100% configured loss drops all packets."""
    expected_loss = 100
    set_link(1, delay_ms=0, loss_pct=100, rate_kbit=1000)
    time.sleep(2)

    loss, _ = ping("drone1_app", "172.31.0.12", count=10)
    assert loss == expected_loss, f"100% loss link showed {loss}% loss"


def test_link_down_drops_all():
    """link_down API produces 100% loss."""
    expected_loss = 100
    link_down(1)
    time.sleep(2)

    loss, _ = ping("drone1_app", "172.31.0.12", count=5)
    assert loss == expected_loss, f"link_down showed {loss}% loss"


def test_link_up_restores():
    """link_up after link_down restores connectivity."""
    expected_max_loss = 0
    link_down(1)
    time.sleep(2)
    link_up(1)
    time.sleep(2)

    loss, _ = ping("drone1_app", "172.31.0.12", count=5)
    assert loss <= expected_max_loss, (
        f"link_up did not restore connectivity: {loss}% loss"
    )
