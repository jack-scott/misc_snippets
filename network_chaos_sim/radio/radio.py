#!/usr/bin/env python3
"""
Radio Sidecar - Network chaos injection and connectivity monitoring.

This container acts as the drone's "radio" interface:
- Applies tc netem rules for network chaos (latency, loss, bandwidth)
- Runs periodic connectivity probes (ping, UDP, TCP) to other drones
- Exposes HTTP API for chaos control
- Writes metrics to shared volume
"""

import json
import os
import socket
import subprocess
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

DRONE_ID = int(os.environ.get("DRONE_ID", 1))
DRONE_COUNT = int(os.environ.get("DRONE_COUNT", 3))
METRICS_DIR = Path("/metrics")
PROBE_INTERVAL = 2  # seconds

# Current chaos settings per target drone
# {target_id: {"latency_ms": 0, "loss_percent": 0, "rate_kbit": 0}}
chaos_settings = {}

# Latest probe results
# {target_id: {"ping_ms": float, "udp_ok": bool, "tcp_ok": bool, "timestamp": float}}
probe_results = {}


def get_other_drones():
    """Get list of other drone IDs."""
    return [i for i in range(1, DRONE_COUNT + 1) if i != DRONE_ID]


def get_drone_ip(drone_id):
    """Get IP address of another drone's radio on the MANET."""
    return f"172.31.0.1{drone_id}"


def run_cmd(cmd, check=False):
    """Run shell command and return output."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=5
        )
        if check and result.returncode != 0:
            print(f"Command failed: {cmd}\n{result.stderr}")
        return result.returncode == 0, result.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "timeout"


def apply_netem(target_id, latency_ms=0, jitter_ms=0, loss_percent=0, rate_kbit=0):
    """Apply tc netem rules for traffic to a specific drone."""
    target_ip = get_drone_ip(target_id)
    interface = "eth0"  # MANET interface

    # Remove existing rules for this target
    run_cmd(f"tc filter del dev {interface} parent 1: prio 1 2>/dev/null")

    # Build netem parameters
    netem_params = []
    if latency_ms > 0:
        if jitter_ms > 0:
            netem_params.append(f"delay {latency_ms}ms {jitter_ms}ms")
        else:
            netem_params.append(f"delay {latency_ms}ms")
    if loss_percent > 0:
        netem_params.append(f"loss {loss_percent}%")
    if rate_kbit > 0:
        netem_params.append(f"rate {rate_kbit}kbit")

    if not netem_params:
        # Clear all rules if no chaos
        run_cmd(f"tc qdisc del dev {interface} root 2>/dev/null")
        chaos_settings[target_id] = {}
        return True

    # Apply new rules
    # First, set up the root qdisc if not present
    run_cmd(f"tc qdisc del dev {interface} root 2>/dev/null")
    run_cmd(f"tc qdisc add dev {interface} root handle 1: prio")

    # Add netem qdisc
    netem_str = " ".join(netem_params)
    ok, _ = run_cmd(
        f"tc qdisc add dev {interface} parent 1:1 handle 10: netem {netem_str}"
    )

    if ok:
        # Add filter to match traffic to target IP
        run_cmd(
            f"tc filter add dev {interface} parent 1: protocol ip prio 1 "
            f"u32 match ip dst {target_ip}/32 flowid 1:1"
        )
        chaos_settings[target_id] = {
            "latency_ms": latency_ms,
            "jitter_ms": jitter_ms,
            "loss_percent": loss_percent,
            "rate_kbit": rate_kbit,
        }
        print(f"Applied chaos to drone {target_id}: {netem_str}")
        return True
    return False


def probe_ping(target_id):
    """Ping another drone and return latency in ms."""
    target_ip = get_drone_ip(target_id)
    ok, output = run_cmd(f"ping -c 1 -W 2 {target_ip}")
    if ok and "time=" in output:
        # Parse: "time=0.123 ms"
        try:
            time_str = output.split("time=")[1].split()[0]
            return float(time_str)
        except (IndexError, ValueError):
            pass
    return -1


def probe_tcp(target_id):
    """Test TCP connectivity to another drone."""
    target_ip = get_drone_ip(target_id)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect((target_ip, 9000))
        sock.send(b"PING\n")
        data = sock.recv(64)
        sock.close()
        return len(data) > 0
    except (socket.error, socket.timeout):
        return False


def probe_udp(target_id):
    """Test UDP connectivity to another drone."""
    target_ip = get_drone_ip(target_id)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2)
        sock.sendto(b"PING", (target_ip, 9001))
        data, _ = sock.recvfrom(64)
        sock.close()
        return len(data) > 0
    except (socket.error, socket.timeout):
        return False


def probe_loop():
    """Continuously probe other drones."""
    while True:
        for target_id in get_other_drones():
            ping_ms = probe_ping(target_id)
            tcp_ok = probe_tcp(target_id)
            udp_ok = probe_udp(target_id)

            probe_results[target_id] = {
                "ping_ms": ping_ms,
                "tcp_ok": tcp_ok,
                "udp_ok": udp_ok,
                "timestamp": time.time(),
            }

        # Write metrics to file
        write_metrics()
        time.sleep(PROBE_INTERVAL)


def write_metrics():
    """Write current metrics to shared volume."""
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    metrics_file = METRICS_DIR / f"drone{DRONE_ID}.json"

    data = {
        "drone_id": DRONE_ID,
        "timestamp": time.time(),
        "probes": probe_results,
        "chaos": chaos_settings,
    }

    with open(metrics_file, "w") as f:
        json.dump(data, f)


class RadioHandler(BaseHTTPRequestHandler):
    """HTTP API for chaos control."""

    def log_message(self, format, *args):
        pass  # Suppress request logging

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/status":
            self.send_json({
                "drone_id": DRONE_ID,
                "probes": probe_results,
                "chaos": chaos_settings,
            })
        elif self.path == "/probes":
            self.send_json(probe_results)
        elif self.path == "/chaos":
            self.send_json(chaos_settings)
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        # POST /chaos/{target_id}
        if self.path.startswith("/chaos/"):
            try:
                target_id = int(self.path.split("/")[2])
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                params = json.loads(body) if body else {}

                ok = apply_netem(
                    target_id,
                    latency_ms=params.get("latency_ms", 0),
                    jitter_ms=params.get("jitter_ms", 0),
                    loss_percent=params.get("loss_percent", 0),
                    rate_kbit=params.get("rate_kbit", 0),
                )
                self.send_json({"ok": ok, "chaos": chaos_settings.get(target_id, {})})
            except (ValueError, json.JSONDecodeError) as e:
                self.send_json({"error": str(e)}, 400)
        else:
            self.send_json({"error": "not found"}, 404)

    def do_DELETE(self):
        # DELETE /chaos/{target_id}
        if self.path.startswith("/chaos/"):
            try:
                target_id = int(self.path.split("/")[2])
                apply_netem(target_id)  # Clear chaos
                self.send_json({"ok": True})
            except ValueError as e:
                self.send_json({"error": str(e)}, 400)
        else:
            self.send_json({"error": "not found"}, 404)


def start_tcp_server():
    """Start a simple TCP server for probing by other drones."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", 9000))
    server.listen(5)
    print(f"TCP probe server listening on port 9000")

    while True:
        try:
            conn, addr = server.accept()
            conn.recv(64)
            conn.send(f"DRONE{DRONE_ID}_TCP_OK\n".encode())
            conn.close()
        except Exception:
            pass


def start_udp_server():
    """Start a simple UDP server for probing by other drones."""
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("0.0.0.0", 9001))
    print(f"UDP probe server listening on port 9001")

    while True:
        try:
            data, addr = server.recvfrom(64)
            server.sendto(f"DRONE{DRONE_ID}_UDP_OK\n".encode(), addr)
        except Exception:
            pass


def main():
    print(f"Radio sidecar starting for drone {DRONE_ID} (of {DRONE_COUNT})")
    print(f"MANET IP: {get_drone_ip(DRONE_ID)}")
    print(f"Other drones: {get_other_drones()}")

    # Start probe servers
    threading.Thread(target=start_tcp_server, daemon=True).start()
    threading.Thread(target=start_udp_server, daemon=True).start()

    # Start probe loop
    threading.Thread(target=probe_loop, daemon=True).start()

    # Start HTTP API
    server = HTTPServer(("0.0.0.0", 8080), RadioHandler)
    print(f"Radio API listening on port 8080")
    server.serve_forever()


if __name__ == "__main__":
    main()
