"""
Backhaul transport: publishes pose and state to foxglove_logger over the
control network (not the degraded MANET). foxglove_logger forwards them as
Foxglove WebSocket channels so Foxglove Studio can visualise them.

The foxglove_logger is reachable at FOXGLOVE_LOGGER_URL via the Docker
control network (manet_control), bypassing tc/netem entirely.

Foxglove WS topics published (via foxglove_logger):
  /drone{N}/backhaul/pose   — foxglove.PoseInFrame-compatible JSON
  /drone{N}/backhaul/state  — flight state string
"""

import math
import os
import threading
import time

import requests

DRONE_ID = int(os.environ.get("DRONE_ID", 1))
LOGGER_URL = os.environ.get("FOXGLOVE_LOGGER_URL", "http://foxglove_logger:9090")
RADIO_URL = "http://localhost:8080"  # radio sidecar, same network namespace


def _make_pose_json(x, y, z, yaw, t):
    ns = int(t * 1e9)
    return {
        "timestamp": {"sec": ns // 1_000_000_000, "nsec": ns % 1_000_000_000},
        "frame_id": "world",
        "pose": {
            "position": {"x": x, "y": y, "z": z},
            "orientation": {
                "x": 0.0,
                "y": 0.0,
                "z": math.sin(yaw / 2),
                "w": math.cos(yaw / 2),
            },
        },
    }


class BackhaulTransport:
    def __init__(self):
        self._session = requests.Session()
        self._pose_url = f"{LOGGER_URL}/drone/{DRONE_ID}/pose"
        self._state_url = f"{LOGGER_URL}/drone/{DRONE_ID}/state"
        self._last_state = None

    def report_pose(self, x, y, z, yaw, timestamp):
        try:
            self._session.post(self._pose_url, json=_make_pose_json(x, y, z, yaw, timestamp), timeout=0.5)
        except requests.RequestException:
            pass

    def report_state(self, state_name):
        if state_name == self._last_state:
            return
        self._last_state = state_name
        try:
            self._session.post(self._state_url, json={"state": state_name, "drone_id": DRONE_ID}, timeout=0.5)
        except requests.RequestException:
            pass

    def update_radio_position(self, x, y, z):
        """Push current position to the radio sidecar so link quality and the UI reflect FC state."""
        try:
            self._session.post(
                f"{RADIO_URL}/position",
                json={"x": x, "y": y, "z": z},
                timeout=0.5,
            )
        except requests.RequestException:
            pass
