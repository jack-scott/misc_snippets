#!/usr/bin/env python3
"""
Foxglove Logger - Central metrics aggregator, backhaul relay, and WS server.

WebSocket :8765  — Foxglove Studio connects here.
HTTP      :9090  — Drone apps and radios POST data here.

Channels:
  /tf_static                  — FrameTransforms: static world frame at 1 Hz (REP-105 root)
  /drone{N}/backhaul/pose     — PoseInFrame: drone position in world frame at 10 Hz
  /drone{N}/backhaul/state    — JSON: flight state on change
  /drone{N}/cmd/takeoff       — schema: {altitude: float}  (publish to command drone)
  /drone{N}/cmd/land          — schema: {}                 (publish {} to land)
  /drone{N}/cmd/orbit         — schema: PoseInFrame-shaped, x/y = centre, z = altitude + radius
  /probe_metrics              — JSON array: per-link radio probe results at 1 Hz
  /network_state              — JSON array: per-drone link quality + traffic at 1 Hz
  /message_events             — JSON: app-layer message delivery events
"""

import json
import os
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import requests
import foxglove
from foxglove import Channel
from foxglove.channels import FrameTransformsChannel, PoseInFrameChannel
from foxglove.messages import (
    FrameTransform,
    FrameTransforms,
    Pose,
    PoseInFrame,
    Quaternion,
    Timestamp,
    Vector3,
)
from foxglove.websocket import Capability, ServerListener

METRICS_DIR = Path("/metrics")
RECORDINGS_DIR = Path("/recordings")
DRONE_COUNT = int(os.environ.get("DRONE_COUNT", 3))
RECORD_MCAP = os.environ.get("RECORD_MCAP", "").lower() in ("1", "true", "yes")

# --- Static channels ---

tf_static_channel = FrameTransformsChannel("/tf_static")
msg_events_channel = Channel("/message_events", message_encoding="json")
probe_channel = Channel("/probe_metrics", message_encoding="json")
network_state_channel = Channel("/network_state", message_encoding="json")

# --- Per-drone command channels ---
# Created at startup for all drones. These serve two purposes:
#   1. Foxglove Studio's Publish panel reads their schema when you select the topic
#   2. Received commands are echoed back so they're visible in Raw Messages

_ORBIT_SCHEMA = {
    "type": "object",
    "title": "OrbitCommand",
    "description": "Orbit centre. pose.position.x/y = centre, z = altitude and radius.",
    "properties": {
        "timestamp": {
            "type": "object",
            "properties": {
                "sec": {"type": "integer"},
                "nsec": {"type": "integer"},
            },
        },
        "frame_id": {"type": "string"},
        "pose": {
            "type": "object",
            "properties": {
                "position": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                        "z": {"type": "number", "description": "Altitude and orbit radius"},
                    },
                },
                "orientation": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                        "z": {"type": "number"},
                        "w": {"type": "number"},
                    },
                },
            },
        },
    },
}

_cmd_channels: dict[int, dict[str, Channel]] = {
    drone_id: {
        "takeoff": Channel(
            f"/drone{drone_id}/cmd/takeoff",
            schema={
                "type": "object",
                "title": "Takeoff",
                "properties": {"altitude": {"type": "number"}},
                "required": ["altitude"],
            },
            message_encoding="json",
        ),
        "land": Channel(
            f"/drone{drone_id}/cmd/land",
            schema={},  # empty schema — publish {} to trigger
            message_encoding="json",
        ),
        "orbit": Channel(
            f"/drone{drone_id}/cmd/orbit",
            schema=_ORBIT_SCHEMA,
            message_encoding="json",
        ),
    }
    for drone_id in range(1, DRONE_COUNT + 1)
}

# --- Per-drone backhaul channels (created lazily on first POST) ---

_drone_pose_channels: dict[int, PoseInFrameChannel] = {}
_drone_state_channels: dict[int, Channel] = {}
_drone_channels_lock = threading.Lock()


def _get_pose_channel(drone_id: int) -> PoseInFrameChannel:
    with _drone_channels_lock:
        if drone_id not in _drone_pose_channels:
            _drone_pose_channels[drone_id] = PoseInFrameChannel(f"/drone{drone_id}/backhaul/pose")
        return _drone_pose_channels[drone_id]


def _get_state_channel(drone_id: int) -> Channel:
    with _drone_channels_lock:
        if drone_id not in _drone_state_channels:
            _drone_state_channels[drone_id] = Channel(
                f"/drone{drone_id}/backhaul/state", message_encoding="json"
            )
        return _drone_state_channels[drone_id]


# --- TF ---

def _make_timestamp(t: float) -> Timestamp:
    ns = int(t * 1e9)
    return Timestamp(sec=ns // 1_000_000_000, nsec=ns % 1_000_000_000)


def _publish_world_tf_static(t: float):
    tf_static_channel.log(FrameTransforms(transforms=[
        FrameTransform(
            timestamp=_make_timestamp(t),
            parent_frame_id="",
            child_frame_id="world",
            translation=Vector3(x=0.0, y=0.0, z=0.0),
            rotation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
        )
    ]))


# --- Metrics loop ---

def metrics_loop():
    while True:
        probes = []
        network_states = []

        for drone_id in range(1, DRONE_COUNT + 1):
            path = METRICS_DIR / f"drone{drone_id}.json"
            if not path.exists():
                continue
            try:
                with open(path) as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError):
                continue

            for target_str, probe in data.get("probes", {}).items():
                probes.append({
                    "drone_id": drone_id,
                    "target_id": int(target_str),
                    "ping_ms": probe.get("ping_ms", -1),
                    "tcp_ok": probe.get("tcp_ok", False),
                    "udp_ok": probe.get("udp_ok", False),
                    "reachable": probe.get("reachable", False),
                    "expected_latency_ms": probe.get("expected_latency_ms", 0),
                    "expected_loss_percent": probe.get("expected_loss_percent", 0),
                    "distance_m": probe.get("distance_m", 0),
                    "tx_bytes_sec": probe.get("tx_bytes_sec", 0),
                    "tx_packets_sec": probe.get("tx_packets_sec", 0),
                    "dropped_sec": probe.get("dropped_sec", 0),
                })

            network_states.append({
                "drone_id": drone_id,
                "environment": data.get("environment", ""),
                "topology": data.get("topology", ""),
                "bandwidth_kbps": data.get("bandwidth_kbps", 0),
                "traffic": data.get("traffic", {}),
                "link_quality": data.get("link_quality", {}),
            })

        if probes:
            probe_channel.log({"probes": probes})
        if network_states:
            network_state_channel.log({"nodes": network_states})

        _publish_world_tf_static(time.time())
        time.sleep(1)


# --- Command routing ---

def _to_fc_command(cmd: str, payload: dict) -> dict | None:
    if cmd == "takeoff":
        return {"command": "takeoff", "altitude": payload.get("altitude", 10.0)}
    if cmd == "land":
        return {"command": "land"}
    if cmd == "orbit":
        pos = payload.get("pose", {}).get("position", {})
        z = float(pos.get("z", 10.0))
        return {"command": "orbit", "center_x": pos.get("x", 0.0), "center_y": pos.get("y", 0.0), "altitude": z}
    return None


class CommandListener(ServerListener):
    def __init__(self):
        self._client_channels: dict[int, str] = {}  # client_channel_id -> topic
        self._lock = threading.Lock()

    def on_client_advertise(self, client, channel) -> None:
        with self._lock:
            self._client_channels[channel.id] = channel.topic

    def on_client_unadvertise(self, client, client_channel_id: int) -> None:
        with self._lock:
            self._client_channels.pop(client_channel_id, None)

    def on_message_data(self, client, client_channel_id: int, data: bytes) -> None:
        with self._lock:
            topic = self._client_channels.get(client_channel_id)
        if topic is None:
            return

        # /drone{N}/cmd/{command}
        parts = topic.strip("/").split("/")
        if len(parts) != 3 or parts[1] != "cmd":
            return
        try:
            drone_id = int(parts[0].replace("drone", ""))
        except ValueError:
            return
        cmd = parts[2]

        try:
            payload = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        # Echo back on the server channel so Raw Messages panel shows it
        if drone_id in _cmd_channels and cmd in _cmd_channels[drone_id]:
            _cmd_channels[drone_id][cmd].log(payload)

        fc_cmd = _to_fc_command(cmd, payload)
        if fc_cmd is None:
            print(f"[logger] unknown command '{cmd}' on {topic}")
            return

        url = f"http://drone{drone_id}_radio:8090/command"
        try:
            resp = requests.post(url, json=fc_cmd, timeout=1.0)
            print(f"[logger] {topic} → drone {drone_id}: {resp.json()}")
        except requests.RequestException as e:
            print(f"[logger] failed to forward to drone {drone_id}: {e}")


# --- HTTP ingest server ---

class LogHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_GET(self):
        if self.path == "/health":
            self.send_json({"ok": True, "drone_count": DRONE_COUNT})
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        parts = self.path.strip("/").split("/")

        # POST /drone/{id}/pose  — FC app reports position at 10 Hz
        if len(parts) == 3 and parts[0] == "drone" and parts[2] == "pose":
            try:
                drone_id = int(parts[1])
            except ValueError:
                self.send_json({"error": "invalid drone id"}, 400)
                return
            data = self.read_json()
            ts = data.get("timestamp", {})
            pos = data.get("pose", {}).get("position", {})
            orient = data.get("pose", {}).get("orientation", {})
            _get_pose_channel(drone_id).log(PoseInFrame(
                timestamp=Timestamp(sec=ts.get("sec", 0), nsec=ts.get("nsec", 0)),
                frame_id=data.get("frame_id", "world"),
                pose=Pose(
                    position=Vector3(x=pos.get("x", 0.0), y=pos.get("y", 0.0), z=pos.get("z", 0.0)),
                    orientation=Quaternion(
                        x=orient.get("x", 0.0), y=orient.get("y", 0.0),
                        z=orient.get("z", 0.0), w=orient.get("w", 1.0),
                    ),
                ),
            ))
            self.send_json({"ok": True})

        # POST /drone/{id}/state
        elif len(parts) == 3 and parts[0] == "drone" and parts[2] == "state":
            try:
                drone_id = int(parts[1])
            except ValueError:
                self.send_json({"error": "invalid drone id"}, 400)
                return
            _get_state_channel(drone_id).log(self.read_json())
            self.send_json({"ok": True})

        # POST /log  — app-layer message delivery event
        elif self.path == "/log":
            data = self.read_json()
            msg_events_channel.log({
                "source": data.get("source"),
                "target": data.get("target"),
                "message_id": data.get("message_id", ""),
                "event": data.get("event", ""),
                "latency_ms": data.get("latency_ms"),
                "payload_size": data.get("payload_size"),
                "strategy": data.get("strategy", "default"),
                "timestamp": data.get("timestamp", time.time()),
                "extra": data.get("extra", {}),
            })
            self.send_json({"ok": True})

        else:
            self.send_json({"error": "not found"}, 404)


@contextmanager
def maybe_mcap():
    if RECORD_MCAP:
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        fname = RECORDINGS_DIR / f"session_{int(time.time())}.mcap"
        print(f"Recording to {fname}")
        with foxglove.open_mcap(str(fname)):
            yield
    else:
        yield


def main():
    with maybe_mcap():
        foxglove.start_server(
            host="0.0.0.0",
            port=8765,
            capabilities=[Capability.ClientPublish],
            supported_encodings=["json"],
            server_listener=CommandListener(),
        )
        threading.Thread(target=metrics_loop, daemon=True).start()

        server = HTTPServer(("0.0.0.0", 9090), LogHandler)
        print("Foxglove logger started")
        print("  WebSocket (Foxglove Studio): ws://localhost:8765")
        print("  HTTP ingest:                 http://localhost:9090")
        print(f"  MCAP recording: {'enabled' if RECORD_MCAP else 'disabled'}")
        print()
        print("3D panel topics: /tf_static  /drone{N}/backhaul/pose")
        print()
        print("Publish panel commands:")
        print("  /drone1/cmd/takeoff  →  {\"altitude\": 10.0}")
        print("  /drone1/cmd/land     →  {}")
        print("  /drone1/cmd/orbit    →  {\"pose\": {\"position\": {\"x\": 0, \"y\": 0, \"z\": 10}}}")
        server.serve_forever()


if __name__ == "__main__":
    main()
