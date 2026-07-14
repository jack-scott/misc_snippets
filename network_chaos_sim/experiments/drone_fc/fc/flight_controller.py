#!/usr/bin/env python3
"""
Flight Controller Simulator

Simulates a drone flight controller with three transport layers:
  - Inter-drone:  Zenoh over MANET (degraded channel, tcp/172.31.0.1N:7447)
  - Intra-drone:  Zenoh on localhost (unrestricted, tcp/127.0.0.1:7448)
  - Backhaul:     HTTP to foxglove_logger (control network, no degradation)

HTTP command server on :8090 receives commands forwarded by foxglove_logger.

Commands (JSON):
  {"command": "takeoff", "altitude": 10.0}
  {"command": "land"}
  {"command": "orbit", "center_x": 0, "center_y": 0, "altitude": 10.0}
"""

import json
import math
import os
import threading
import time
from enum import Enum
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import yaml

from transport_backhaul import BackhaulTransport
from transport_inter import InterTransport
from transport_intra import IntraTransport

DRONE_ID = int(os.environ.get("DRONE_ID", 1))
DRONE_COUNT = int(os.environ.get("DRONE_COUNT", 3))
CONFIG_PATH = Path("/config/config.yaml")
UPDATE_HZ = 10
MANEUVER_DURATION_S = 3.0


class FlightState(Enum):
    LANDED = "landed"
    TAKING_OFF = "taking_off"
    HOVERING = "hovering"
    LANDING = "landing"
    CIRCLING = "circling"


def _load_start_position():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            cfg = yaml.safe_load(f) or {}
        positions = cfg.get("defaults", {}).get("positions", {})
        pos = positions.get(DRONE_ID) or positions.get(str(DRONE_ID)) or {}
        return float(pos.get("x", 0.0)), float(pos.get("y", 0.0))
    return 0.0, 0.0


class FlightController:
    def __init__(self):
        start_x, start_y = _load_start_position()
        self.x = start_x
        self.y = start_y
        self.z = 0.0
        self.yaw = 0.0
        self.state = FlightState.LANDED

        self._target_alt = 0.0
        self._alt_at_maneuver_start = 0.0
        self._maneuver_start_t = 0.0

        self._circle_cx = 0.0
        self._circle_cy = 0.0
        self._circle_radius = 50.0
        self._circle_angle = 0.0
        self._circle_speed = 0.15  # rad/s

        self._lock = threading.Lock()

    # --- Commands ---

    def takeoff(self, altitude):
        with self._lock:
            if self.state != FlightState.LANDED:
                return {"ok": False, "error": f"cannot takeoff from {self.state.value}"}
            self._target_alt = float(altitude)
            self._alt_at_maneuver_start = self.z
            self._maneuver_start_t = time.time()
            self.state = FlightState.TAKING_OFF
            print(f"[FC] drone {DRONE_ID}: taking off to {altitude}m")
            return {"ok": True}

    def land(self):
        with self._lock:
            if self.state not in (FlightState.HOVERING, FlightState.CIRCLING):
                return {"ok": False, "error": f"cannot land from {self.state.value}"}
            self._alt_at_maneuver_start = self.z
            self._maneuver_start_t = time.time()
            self.state = FlightState.LANDING
            print(f"[FC] drone {DRONE_ID}: landing from {self.z:.1f}m")
            return {"ok": True}

    def orbit(self, center_x, center_y, altitude):
        with self._lock:
            if self.state not in (FlightState.HOVERING, FlightState.CIRCLING):
                return {"ok": False, "error": f"cannot orbit from {self.state.value}"}
            self._circle_cx = float(center_x)
            self._circle_cy = float(center_y)
            self._circle_radius = float(altitude)  # radius == altitude
            self._alt_at_maneuver_start = self.z
            self._target_alt = float(altitude)
            self._maneuver_start_t = time.time()
            self._circle_angle = math.atan2(self.y - self._circle_cy, self.x - self._circle_cx)
            self.state = FlightState.CIRCLING
            print(f"[FC] drone {DRONE_ID}: orbit centre=({center_x},{center_y}) alt/r={altitude}m")
            return {"ok": True}

    # --- Simulation ---

    def update(self, dt):
        with self._lock:
            if self.state == FlightState.TAKING_OFF:
                ratio = min(1.0, (time.time() - self._maneuver_start_t) / MANEUVER_DURATION_S)
                self.z = self._alt_at_maneuver_start + ratio * (self._target_alt - self._alt_at_maneuver_start)
                if ratio >= 1.0:
                    self.state = FlightState.HOVERING
                    print(f"[FC] drone {DRONE_ID}: hovering at {self.z:.1f}m")

            elif self.state == FlightState.LANDING:
                ratio = min(1.0, (time.time() - self._maneuver_start_t) / MANEUVER_DURATION_S)
                self.z = self._alt_at_maneuver_start * (1.0 - ratio)
                if ratio >= 1.0:
                    self.z = 0.0
                    self.state = FlightState.LANDED
                    print(f"[FC] drone {DRONE_ID}: landed")

            elif self.state == FlightState.CIRCLING:
                self._circle_angle += self._circle_speed * dt
                self.x = self._circle_cx + self._circle_radius * math.cos(self._circle_angle)
                self.y = self._circle_cy + self._circle_radius * math.sin(self._circle_angle)
                self.yaw = self._circle_angle + math.pi / 2

    def get_pose(self):
        with self._lock:
            return self.x, self.y, self.z, self.yaw, self.state.value


# --- HTTP Command Server ---

class _CommandHandler(BaseHTTPRequestHandler):
    controller: "FlightController"

    def log_message(self, *_):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/command":
            self.send_json({"error": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(length)) if length else {}
        cmd = data.get("command")

        if cmd == "takeoff":
            result = self.controller.takeoff(data.get("altitude", 10.0))
        elif cmd == "land":
            result = self.controller.land()
        elif cmd == "orbit":
            result = self.controller.orbit(
                data.get("center_x", 0.0),
                data.get("center_y", 0.0),
                data.get("altitude", 10.0),
            )
        else:
            result = {"ok": False, "error": f"unknown command: {cmd}"}

        self.send_json(result)


def _make_command_handler(controller):
    class Handler(_CommandHandler):
        pass
    Handler.controller = controller
    return Handler


def _run_command_server(controller):
    server = HTTPServer(("0.0.0.0", 8090), _make_command_handler(controller))
    print(f"[FC] drone {DRONE_ID}: command server listening on :8090")
    server.serve_forever()


# --- Main Loop ---

def main():
    print(f"[FC] drone {DRONE_ID} starting ({DRONE_COUNT} total drones)")

    fc = FlightController()

    backhaul = BackhaulTransport()
    intra = IntraTransport()
    inter = InterTransport()

    intra.start()
    inter.start()

    threading.Thread(target=_run_command_server, args=(fc,), daemon=True).start()

    interval = 1.0 / UPDATE_HZ
    radio_update_interval = 1.0  # 1 Hz — radio calls apply_link_rules (tc), keep it cheap
    prev_state = None
    last_t = time.time()
    last_radio_update = 0.0

    print(f"[FC] drone {DRONE_ID}: running at {UPDATE_HZ}Hz")

    while True:
        now = time.time()
        dt = now - last_t
        last_t = now

        fc.update(dt)
        x, y, z, yaw, state_name = fc.get_pose()

        backhaul.report_pose(x, y, z, yaw, now)
        inter.publish(x, y, z, yaw, now)
        intra.publish_pose(x, y, z, yaw, now)

        if state_name != prev_state:
            backhaul.report_state(state_name)
            intra.publish_state(state_name)
            prev_state = state_name

        if now - last_radio_update >= radio_update_interval:
            backhaul.update_radio_position(x, y, z)
            last_radio_update = now

        time.sleep(max(0, interval - (time.time() - now)))


if __name__ == "__main__":
    main()
