"""Internal traffic unaffected by spoke shaping.

Verifies that communication between a drone's own containers (app <-> radio
on the internal bridge) has no added latency or loss, even with aggressive
shaping on the radio's manet link.
"""

import time

import pytest

from conftest import ping, set_link

pytestmark = pytest.mark.usefixtures("reset_links")

MAX_RTT_MS = 5
MAX_LOSS_PCT = 0


def test_internal_ping_unaffected_by_heavy_shaping(simulator):
    """Internal bridge ping stays fast and lossless under heavy shaping."""
    set_link(1, delay_ms=200, loss_pct=50, rate_kbit=100)
    time.sleep(2)

    loss, avg_rtt = ping("drone1_app", "10.1.0.2", count=20)

    assert loss <= MAX_LOSS_PCT, (
        f"Internal loss {loss}% exceeds threshold {MAX_LOSS_PCT}%"
    )
    assert avg_rtt is not None, "No RTT measured (all packets lost)"
    assert avg_rtt <= MAX_RTT_MS, (
        f"Internal avg RTT {avg_rtt}ms exceeds threshold {MAX_RTT_MS}ms"
    )
