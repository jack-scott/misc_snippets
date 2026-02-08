"""Fixtures for radio.py unit tests."""

import os
import sys
import pytest

# Set required env vars before importing radio
os.environ["DRONE_ID"] = "1"
os.environ["DRONE_COUNT"] = "3"

# Add radio directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "radio"))

import radio


@pytest.fixture(autouse=True)
def reset_state():
    """Reset radio state between tests."""
    radio.state.positions = {}
    radio.state.environment = "clear"
    radio.state.topology = "mesh"
    radio.state.link_quality = {}
    radio.state.link_overrides = {}
    radio.state.direct_link_params = {}
    radio.state.link_down = False
    radio.state.bandwidth_override = None
    radio.state.prev_traffic = {}
    radio.state.prev_time = 0
    radio.state.traffic_stats = {
        "tx_bytes": 0, "rx_bytes": 0,
        "tx_packets": 0, "rx_packets": 0,
        "tx_bytes_sec": 0, "rx_bytes_sec": 0,
        "tx_packets_sec": 0, "rx_packets_sec": 0,
        "load_percent": 0.0,
    }
    radio.state.link_traffic = {}
    radio.state.tc_class_map = {}

    # Re-initialize positions
    radio.init_positions()

    yield
