"""
Intra-drone transport over localhost using Zenoh.

Binds on 127.0.0.1:7448 so traffic never leaves the drone's network namespace
and is completely unaffected by the MANET tc/netem rules.

Other processes on the same drone (sharing the same network namespace) can
connect to tcp/127.0.0.1:7448 to receive pose/state updates.

Message format: foxglove.PoseInFrame serialised as protobuf bytes.
Zenoh key expressions:
  publish: drone/{DRONE_ID}/intra/pose
           drone/{DRONE_ID}/intra/state
"""

import json
import math
import os
import threading
import time

DRONE_ID = int(os.environ.get("DRONE_ID", 1))

try:
    import zenoh
    HAS_ZENOH = True
except ImportError:
    HAS_ZENOH = False
    print("[intra] zenoh not available")

try:
    from foxglove.messages import PoseInFrame, Pose, Vector3, Quaternion
    from google.protobuf.timestamp_pb2 import Timestamp
    HAS_PROTO = True
except ImportError:
    HAS_PROTO = False
    print("[intra] foxglove.messages not available, using JSON fallback")


def _serialise_pose(x, y, z, yaw, t):
    if HAS_PROTO:
        ns = int(t * 1e9)
        return PoseInFrame(
            timestamp=Timestamp(seconds=ns // 1_000_000_000, nanos=ns % 1_000_000_000),
            frame_id="world",
            pose=Pose(
                position=Vector3(x=x, y=y, z=z),
                orientation=Quaternion(x=0.0, y=0.0, z=math.sin(yaw / 2), w=math.cos(yaw / 2)),
            ),
        ).SerializeToString()
    ns = int(t * 1e9)
    return json.dumps({
        "timestamp": {"sec": ns // 1_000_000_000, "nsec": ns % 1_000_000_000},
        "frame_id": "world",
        "pose": {
            "position": {"x": x, "y": y, "z": z},
            "orientation": {"x": 0.0, "y": 0.0, "z": math.sin(yaw / 2), "w": math.cos(yaw / 2)},
        },
    }).encode()


class IntraTransport:
    def __init__(self):
        self._session = None
        self._pose_pub = None
        self._state_pub = None
        self._lock = threading.Lock()

    def start(self):
        threading.Thread(target=self._connect_loop, daemon=True).start()

    def _connect_loop(self):
        while True:
            try:
                self._open_session()
                print("[intra] Zenoh ready on 127.0.0.1:7448")
                return
            except Exception as e:
                print(f"[intra] Zenoh connect failed ({e}), retrying in 3s")
                time.sleep(3)

    def _open_session(self):
        if not HAS_ZENOH:
            return

        conf = zenoh.Config.from_json5(json.dumps({
            "mode": "peer",
            "listen": {"endpoints": ["tcp/127.0.0.1:7448"]},
            "scouting": {"multicast": {"enabled": False}},
        }))

        with self._lock:
            self._session = zenoh.open(conf)
            self._pose_pub = self._session.declare_publisher(f"drone/{DRONE_ID}/intra/pose")
            self._state_pub = self._session.declare_publisher(f"drone/{DRONE_ID}/intra/state")

    def publish_pose(self, x, y, z, yaw, timestamp):
        with self._lock:
            if self._pose_pub is None:
                return
            self._pose_pub.put(_serialise_pose(x, y, z, yaw, timestamp))

    def publish_state(self, state_name):
        with self._lock:
            if self._state_pub is None:
                return
            self._state_pub.put(json.dumps({"state": state_name, "drone_id": DRONE_ID}).encode())
