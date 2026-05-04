"""
Inter-drone transport over MANET using Zenoh.

Listens on the MANET IP (172.31.0.1{N}:7447) so all traffic goes through
the radio sidecar's tc/netem rules and experiences the degraded channel.

Message format: foxglove.PoseInFrame serialised as protobuf bytes.
Zenoh key expressions:
  publish:   drone/{DRONE_ID}/inter/pose
  subscribe: drone/*/inter/pose
"""

import json
import math
import os
import threading
import time

DRONE_ID = int(os.environ.get("DRONE_ID", 1))
DRONE_COUNT = int(os.environ.get("DRONE_COUNT", 3))
MANET_IP = f"172.31.0.1{DRONE_ID}"

try:
    import zenoh
    HAS_ZENOH = True
except ImportError:
    HAS_ZENOH = False
    print("[inter] zenoh not available")

try:
    from foxglove.messages import PoseInFrame, Pose, Vector3, Quaternion
    from google.protobuf.timestamp_pb2 import Timestamp
    HAS_PROTO = True
except ImportError:
    HAS_PROTO = False
    print("[inter] foxglove.messages not available, using JSON fallback")


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


class InterTransport:
    def __init__(self, on_peer_pose=None):
        """on_peer_pose(peer_id: int, payload: bytes) called on each received peer pose."""
        self._on_peer_pose = on_peer_pose
        self._session = None
        self._pub = None
        self._lock = threading.Lock()

    def start(self):
        threading.Thread(target=self._connect_loop, daemon=True).start()

    def _connect_loop(self):
        while True:
            try:
                self._open_session()
                print(f"[inter] Zenoh ready on {MANET_IP}:7447")
                return
            except Exception as e:
                print(f"[inter] Zenoh connect failed ({e}), retrying in 3s")
                time.sleep(3)

    def _open_session(self):
        if not HAS_ZENOH:
            return

        peers = [f"tcp/172.31.0.1{i}:7447" for i in range(1, DRONE_COUNT + 1) if i != DRONE_ID]
        conf = zenoh.Config.from_json5(json.dumps({
            "mode": "peer",
            "listen": {"endpoints": [f"tcp/{MANET_IP}:7447"]},
            "connect": {"endpoints": peers},
            "scouting": {"multicast": {"enabled": False}},
        }))

        with self._lock:
            self._session = zenoh.open(conf)
            self._pub = self._session.declare_publisher(f"drone/{DRONE_ID}/inter/pose")
            if self._on_peer_pose:
                self._session.declare_subscriber("drone/*/inter/pose", self._handle_peer_pose)

    def _handle_peer_pose(self, sample):
        if not self._on_peer_pose:
            return
        parts = str(sample.key_expr).split("/")
        try:
            peer_id = int(parts[1])
            if peer_id != DRONE_ID:
                self._on_peer_pose(peer_id, bytes(sample.payload))
        except (IndexError, ValueError):
            pass

    def publish(self, x, y, z, yaw, timestamp):
        with self._lock:
            if self._pub is None:
                return
            self._pub.put(_serialise_pose(x, y, z, yaw, timestamp))
