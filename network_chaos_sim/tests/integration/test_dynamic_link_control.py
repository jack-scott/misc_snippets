"""Dynamic link control via API.

Verifies that the controller API can set link parameters and that
ping results reflect the configured loss.
"""

import time

import pytest

from conftest import get_reachable_target, link_down, link_up, ping, set_link

pytestmark = pytest.mark.usefixtures("reset_links")


def test_clean_link_zero_loss(simulator):
    """0% configured loss produces 0% measured loss."""
    expected_loss = 0
    target = get_reachable_target(simulator, 1)
    set_link(1, delay_ms=10, loss_pct=0, rate_kbit=1000)
    time.sleep(2)

    loss, _ = ping("drone1_app", target, count=20)
    assert loss == expected_loss, f"Clean link showed {loss}% loss"


def test_full_loss(simulator):
    """100% configured loss drops all packets."""
    expected_loss = 100
    target = get_reachable_target(simulator, 1)
    set_link(1, delay_ms=0, loss_pct=100, rate_kbit=1000)
    time.sleep(2)

    loss, _ = ping("drone1_app", target, count=10)
    assert loss == expected_loss, f"100% loss link showed {loss}% loss"


def test_link_down_drops_all(simulator):
    """link_down API produces 100% loss."""
    expected_loss = 100
    target = get_reachable_target(simulator, 1)
    link_down(1)
    time.sleep(2)

    loss, _ = ping("drone1_app", target, count=5)
    assert loss == expected_loss, f"link_down showed {loss}% loss"


def test_link_up_restores(simulator):
    """link_up after link_down restores connectivity."""
    expected_max_loss = 0
    target = get_reachable_target(simulator, 1)
    link_down(1)
    time.sleep(2)
    link_up(1)
    time.sleep(2)

    loss, _ = ping("drone1_app", target, count=5)
    assert loss <= expected_max_loss, (
        f"link_up did not restore connectivity: {loss}% loss"
    )
