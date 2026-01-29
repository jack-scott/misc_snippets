#!/usr/bin/env python3
"""
Enhanced Radio Sidecar - Shared bandwidth, position-based degradation, weather profiles.

Features:
- Shared radio bandwidth (HTB qdisc) - total BW split across all links
- Position-based signal degradation
- Environment/weather profiles
- Star and mesh topology support
"""

import json
import math
import os
import socket
import subprocess
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

import yaml

# Configuration
DRONE_ID = int(os.environ.get("DRONE_ID", 1))
DRONE_COUNT = int(os.environ.get("DRONE_COUNT", 3))
METRICS_DIR = Path("/metrics")
CONFIG_DIR = Path("/config")
PROBE_INTERVAL = 2

# Load configuration
def load_config():
    config_file = CONFIG_DIR / "config.yaml"
    if config_file.exists():
        with open(config_file) as f:
            return yaml.safe_load(f)
    return get_default_config()

def get_default_config():
    return {
        "radio": {"bandwidth_kbps": 1000},
        "distance": {
            "max_range_m": 1000,
            "thresholds": [
                {"range_m": 0, "latency_ms": 2, "loss_percent": 0},
                {"range_m": 500, "latency_ms": 30, "loss_percent": 10},
                {"range_m": 1000, "latency_ms": 100, "loss_percent": 40},
            ]
        },
        "environment": {
            "profiles": {
                "clear": {"latency_multiplier": 1.0, "loss_multiplier": 1.0, "bandwidth_multiplier": 1.0}
            }
        },
        "topology": {"default": "mesh"},
        "defaults": {"environment": "clear", "positions": {}}
    }

CONFIG = load_config()

# State
class State:
    positions = {}  # drone_id -> {x, y, z}
    environment = "clear"
    topology = "mesh"
    link_quality = {}  # drone_id -> {latency_ms, loss_percent, bandwidth_kbps}
    link_overrides = {}  # drone_id -> {extra_latency_ms, extra_loss_percent, partition}
    # Traffic stats
    prev_traffic = {}  # For rate calculation
    prev_time = 0
    traffic_stats = {
        "tx_bytes": 0, "rx_bytes": 0,
        "tx_packets": 0, "rx_packets": 0,
        "tx_bytes_sec": 0, "rx_bytes_sec": 0,
        "tx_packets_sec": 0, "rx_packets_sec": 0,
        "load_percent": 0.0,
    }
    link_traffic = {}  # drone_id -> {tx_bytes, tx_packets, tx_bytes_sec, tx_packets_sec, dropped}
    tc_class_map = {}  # class_id -> target_id (set during apply_link_rules)

state = State()

# Initialize positions from config
def init_positions():
    defaults = CONFIG.get("defaults", {}).get("positions", {})
    for drone_id in range(1, DRONE_COUNT + 1):
        if str(drone_id) in defaults:
            state.positions[drone_id] = defaults[str(drone_id)]
        elif drone_id in defaults:
            state.positions[drone_id] = defaults[drone_id]
        else:
            state.positions[drone_id] = {"x": 0, "y": 0, "z": 0}

    # Base station at position 0
    base_pos = CONFIG.get("radio", {}).get("base_station", {}).get("position", {"x": 0, "y": 0, "z": 0})
    state.positions[0] = base_pos

    state.environment = CONFIG.get("defaults", {}).get("environment", "clear")
    state.topology = CONFIG.get("topology", {}).get("default", "mesh")

init_positions()

# Traffic statistics collection
def setup_iptables_accounting():
    """Set up iptables rules to count traffic per destination."""
    # Clear existing accounting rules
    run_cmd("iptables -F OUTPUT 2>/dev/null")
    run_cmd("iptables -F INPUT 2>/dev/null")

    # Add rules for each potential target
    for target_id in range(0, DRONE_COUNT + 1):
        if target_id == DRONE_ID:
            continue
        target_ip = get_drone_ip(target_id)
        # Count outgoing traffic to each peer
        run_cmd(f"iptables -A OUTPUT -d {target_ip} -j ACCEPT")
        # Count incoming traffic from each peer
        run_cmd(f"iptables -A INPUT -s {target_ip} -j ACCEPT")

    print(f"iptables accounting rules configured for {DRONE_COUNT} peers")

def read_interface_stats():
    """Read total interface traffic from /proc/net/dev."""
    iface = MANET_INTERFACE or "eth0"
    try:
        with open("/proc/net/dev") as f:
            for line in f:
                if f"{iface}:" in line:
                    parts = line.split()
                    # Format: iface rx_bytes rx_packets ... tx_bytes tx_packets ...
                    return {
                        "rx_bytes": int(parts[1]),
                        "rx_packets": int(parts[2]),
                        "tx_bytes": int(parts[9]),
                        "tx_packets": int(parts[10]),
                    }
    except (IOError, IndexError, ValueError):
        pass
    return {"rx_bytes": 0, "rx_packets": 0, "tx_bytes": 0, "tx_packets": 0}

def read_tc_class_stats():
    """Read per-class traffic stats from tc (shows actual delivered traffic after netem)."""
    counters = {}

    try:
        # Read qdisc stats - netem qdiscs are children of HTB classes
        # The netem handle matches the class ID it's attached to
        ok, qdisc_output = run_cmd(f"tc -s qdisc show dev {MANET_INTERFACE}")
        if ok:
            current_class_id = None
            for line in qdisc_output.split("\n"):
                if line.startswith("qdisc netem"):
                    # Extract parent class: "qdisc netem 11: parent 1:11 ..."
                    try:
                        parts = line.split()
                        # parent is like "1:11" - extract the class ID
                        parent = parts[4]  # "1:11"
                        current_class_id = int(parent.split(":")[1])
                    except (ValueError, IndexError):
                        current_class_id = None
                elif current_class_id and "Sent" in line:
                    # Parse: " Sent 169486 bytes 2422 pkt (dropped 22, overlimits 0 requeues 0)"
                    try:
                        parts = line.split()
                        bytes_sent = int(parts[1])
                        pkts_sent = int(parts[3])
                        dropped = 0
                        if "dropped" in line:
                            dropped = int(line.split("dropped")[1].split(",")[0].strip())

                        # Map class ID to target drone ID
                        if current_class_id in state.tc_class_map:
                            target_id = state.tc_class_map[current_class_id]
                            counters[target_id] = {
                                "tx_bytes": bytes_sent,
                                "tx_packets": pkts_sent,
                                "dropped": dropped,
                            }
                    except (ValueError, IndexError):
                        pass
                    current_class_id = None
    except Exception as e:
        print(f"Error reading tc stats: {e}")

    return counters

def update_traffic_stats():
    """Update traffic statistics with rate calculations."""
    now = time.time()
    current = read_interface_stats()
    link_counters = read_tc_class_stats()  # Use tc stats for accurate per-link traffic

    if state.prev_time > 0:
        elapsed = now - state.prev_time
        if elapsed > 0:
            # Calculate rates for total interface traffic
            state.traffic_stats["tx_bytes"] = current["tx_bytes"]
            state.traffic_stats["rx_bytes"] = current["rx_bytes"]
            state.traffic_stats["tx_packets"] = current["tx_packets"]
            state.traffic_stats["rx_packets"] = current["rx_packets"]

            prev = state.prev_traffic
            state.traffic_stats["tx_bytes_sec"] = int((current["tx_bytes"] - prev.get("tx_bytes", 0)) / elapsed)
            state.traffic_stats["rx_bytes_sec"] = int((current["rx_bytes"] - prev.get("rx_bytes", 0)) / elapsed)
            state.traffic_stats["tx_packets_sec"] = int((current["tx_packets"] - prev.get("tx_packets", 0)) / elapsed)
            state.traffic_stats["rx_packets_sec"] = int((current["rx_packets"] - prev.get("rx_packets", 0)) / elapsed)

            # Calculate load as percentage of configured bandwidth
            bandwidth_bytes_sec = get_radio_bandwidth() * 1000 / 8  # kbps to bytes/sec
            total_bytes_sec = state.traffic_stats["tx_bytes_sec"] + state.traffic_stats["rx_bytes_sec"]
            state.traffic_stats["load_percent"] = min(100, round(100 * total_bytes_sec / bandwidth_bytes_sec, 1)) if bandwidth_bytes_sec > 0 else 0

            # Calculate per-link rates from tc stats (actual delivered traffic)
            for target_id, counters in link_counters.items():
                prev_link = state.link_traffic.get(target_id, {})
                prev_bytes = prev_link.get("tx_bytes", 0)
                prev_packets = prev_link.get("tx_packets", 0)
                prev_dropped = prev_link.get("dropped", 0)

                # Handle counter reset (when rules are reapplied)
                if counters["tx_bytes"] < prev_bytes:
                    prev_bytes = 0
                    prev_packets = 0
                    prev_dropped = 0

                tx_bytes_sec = int((counters["tx_bytes"] - prev_bytes) / elapsed)
                tx_packets_sec = int((counters["tx_packets"] - prev_packets) / elapsed)
                dropped_sec = int((counters["dropped"] - prev_dropped) / elapsed)

                state.link_traffic[target_id] = {
                    "tx_bytes": counters["tx_bytes"],
                    "tx_packets": counters["tx_packets"],
                    "dropped": counters["dropped"],
                    "tx_bytes_sec": max(0, tx_bytes_sec),
                    "tx_packets_sec": max(0, tx_packets_sec),
                    "dropped_sec": max(0, dropped_sec),
                }

    state.prev_traffic = current
    state.prev_time = now

def get_drone_ip(drone_id):
    """Get IP address of a drone's radio on the MANET."""
    if drone_id == 0:
        return "172.31.0.10"  # Base station
    return f"172.31.0.1{drone_id}"

def get_other_drones():
    """Get list of reachable drone IDs based on topology."""
    if state.topology == "star":
        if DRONE_ID == 0:
            # Base station can reach all drones
            return list(range(1, DRONE_COUNT + 1))
        else:
            # Drones can only reach base station
            return [0]
    else:
        # Mesh: can reach all other drones
        return [i for i in range(1, DRONE_COUNT + 1) if i != DRONE_ID]

def calculate_distance(pos1, pos2):
    """Calculate 3D Euclidean distance between two positions."""
    dx = pos1.get("x", 0) - pos2.get("x", 0)
    dy = pos1.get("y", 0) - pos2.get("y", 0)
    dz = pos1.get("z", 0) - pos2.get("z", 0)
    return math.sqrt(dx*dx + dy*dy + dz*dz)

def interpolate_degradation(distance):
    """Interpolate link quality based on distance using config thresholds."""
    thresholds = CONFIG.get("distance", {}).get("thresholds", [])
    max_range = CONFIG.get("distance", {}).get("max_range_m", 1000)

    if distance >= max_range:
        return None  # Out of range

    if not thresholds:
        return {"latency_ms": 10, "loss_percent": 0}

    # Find surrounding thresholds
    lower = thresholds[0]
    upper = thresholds[-1]

    for i, t in enumerate(thresholds):
        if t["range_m"] <= distance:
            lower = t
        if t["range_m"] >= distance:
            upper = t
            break

    # Interpolate
    if lower["range_m"] == upper["range_m"]:
        return {"latency_ms": lower["latency_ms"], "loss_percent": lower["loss_percent"]}

    ratio = (distance - lower["range_m"]) / (upper["range_m"] - lower["range_m"])
    latency = lower["latency_ms"] + ratio * (upper["latency_ms"] - lower["latency_ms"])
    loss = lower["loss_percent"] + ratio * (upper["loss_percent"] - lower["loss_percent"])

    return {"latency_ms": latency, "loss_percent": loss}

def apply_environment(base_quality):
    """Apply environment multipliers to base link quality."""
    if base_quality is None:
        return None

    profiles = CONFIG.get("environment", {}).get("profiles", {})
    profile = profiles.get(state.environment, {"latency_multiplier": 1.0, "loss_multiplier": 1.0})

    latency = base_quality["latency_ms"] * profile.get("latency_multiplier", 1.0)
    loss = min(100, base_quality["loss_percent"] * profile.get("loss_multiplier", 1.0))

    return {"latency_ms": latency, "loss_percent": loss}

def calculate_link_quality(target_id):
    """Calculate link quality to a target drone based on distance and environment."""
    if DRONE_ID not in state.positions or target_id not in state.positions:
        return {"latency_ms": 10, "loss_percent": 0, "reachable": True}

    distance = calculate_distance(state.positions[DRONE_ID], state.positions[target_id])
    base_quality = interpolate_degradation(distance)

    if base_quality is None:
        return {"latency_ms": 0, "loss_percent": 100, "reachable": False, "distance_m": distance}

    quality = apply_environment(base_quality)
    quality["reachable"] = True
    quality["distance_m"] = distance

    return quality

def get_radio_bandwidth():
    """Get effective radio bandwidth considering environment."""
    base_bw = CONFIG.get("radio", {}).get("bandwidth_kbps", 1000)
    profiles = CONFIG.get("environment", {}).get("profiles", {})
    profile = profiles.get(state.environment, {})
    multiplier = profile.get("bandwidth_multiplier", 1.0)
    return int(base_bw * multiplier)

# TC/HTB Management
def run_cmd(cmd, check=False):
    """Run shell command."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        if check and result.returncode != 0:
            print(f"Command failed: {cmd}\n{result.stderr}")
        return result.returncode == 0, result.stdout.strip()
    except subprocess.TimeoutExpired:
        return False, "timeout"

def get_manet_interface():
    """Find the network interface connected to the MANET mesh (172.31.0.x)."""
    try:
        ok, output = run_cmd("ip -o addr show")
        if ok:
            for line in output.split("\n"):
                if "172.31.0." in line:
                    # Format: "3: eth1    inet 172.31.0.11/24 ..."
                    parts = line.split()
                    if len(parts) >= 2:
                        return parts[1].rstrip(":")
    except Exception:
        pass
    return "eth0"  # Fallback

MANET_INTERFACE = None  # Will be set at startup

def setup_htb_root():
    """Set up HTB qdisc for shared bandwidth control."""
    interface = MANET_INTERFACE
    bandwidth = get_radio_bandwidth()

    # Clear existing rules
    run_cmd(f"tc qdisc del dev {interface} root 2>/dev/null")

    # Create HTB root with total bandwidth limit
    run_cmd(f"tc qdisc add dev {interface} root handle 1: htb default 99")
    run_cmd(f"tc class add dev {interface} parent 1: classid 1:1 htb rate {bandwidth}kbit ceil {bandwidth}kbit")

    # Default class for unclassified traffic
    run_cmd(f"tc class add dev {interface} parent 1:1 classid 1:99 htb rate {bandwidth}kbit ceil {bandwidth}kbit")

    print(f"HTB root configured: {bandwidth} kbit/s total bandwidth")

def apply_link_rules():
    """Apply tc rules for each link based on calculated quality."""
    interface = MANET_INTERFACE
    bandwidth = get_radio_bandwidth()
    targets = get_other_drones()

    # Recalculate all link qualities
    for target_id in range(0, DRONE_COUNT + 1):
        if target_id == DRONE_ID:
            continue
        state.link_quality[target_id] = calculate_link_quality(target_id)

    # Clear existing netem qdiscs, classes, and filters
    for i in range(1, 20):
        # Delete netem qdisc by parent (more reliable than by handle)
        run_cmd(f"tc qdisc del dev {interface} parent 1:{10+i} 2>/dev/null")
        run_cmd(f"tc class del dev {interface} classid 1:{10+i} 2>/dev/null")
        run_cmd(f"tc filter del dev {interface} prio {i} 2>/dev/null")

    # Clear the class mapping
    state.tc_class_map = {}

    # Create class and netem qdisc for each reachable target
    class_id = 10
    for target_id in targets:
        quality = state.link_quality.get(target_id, {})
        override = state.link_overrides.get(target_id, {})
        target_ip = get_drone_ip(target_id)

        if not quality.get("reachable", True) or override.get("partition", False):
            # Unreachable or partitioned: use netem with 100% loss
            latency = 0
            loss = 100
        else:
            # Base quality + any overrides
            latency = int(quality.get("latency_ms", 10)) + int(override.get("extra_latency_ms", 0))
            loss = min(100, int(quality.get("loss_percent", 0)) + int(override.get("extra_loss_percent", 0)))

        class_id += 1

        # Store mapping for traffic stats
        state.tc_class_map[class_id] = target_id

        # Create HTB class (shares parent bandwidth)
        run_cmd(f"tc class add dev {interface} parent 1:1 classid 1:{class_id} htb rate 10kbit ceil {bandwidth}kbit")

        # Add netem qdisc for latency/loss
        netem_params = []
        if latency > 0:
            jitter = max(1, latency // 10)
            netem_params.append(f"delay {latency}ms {jitter}ms")
        if loss > 0:
            netem_params.append(f"loss {loss}%")

        if netem_params:
            netem_str = " ".join(netem_params)
            run_cmd(f"tc qdisc add dev {interface} parent 1:{class_id} handle {class_id}: netem {netem_str}")

        # Filter to direct traffic to this class
        run_cmd(f"tc filter add dev {interface} parent 1: protocol ip prio {class_id - 10} u32 match ip dst {target_ip}/32 flowid 1:{class_id}")

    print(f"Applied link rules for {len(targets)} targets")

# Probe functions
probe_results = {}

def probe_ping(target_id):
    """Ping another drone."""
    target_ip = get_drone_ip(target_id)
    ok, output = run_cmd(f"ping -c 1 -W 2 {target_ip}")
    if ok and "time=" in output:
        try:
            time_str = output.split("time=")[1].split()[0]
            return float(time_str)
        except (IndexError, ValueError):
            pass
    return -1

def probe_tcp(target_id):
    """Test TCP connectivity."""
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
    """Test UDP connectivity."""
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
        # Update traffic statistics
        update_traffic_stats()

        targets = get_other_drones()
        for target_id in targets:
            quality = state.link_quality.get(target_id, {})
            link_traffic = state.link_traffic.get(target_id, {})
            ping_ms = probe_ping(target_id)
            tcp_ok = probe_tcp(target_id)
            udp_ok = probe_udp(target_id)

            probe_results[target_id] = {
                "ping_ms": ping_ms,
                "tcp_ok": tcp_ok,
                "udp_ok": udp_ok,
                "distance_m": quality.get("distance_m", 0),
                "expected_latency_ms": quality.get("latency_ms", 0),
                "expected_loss_percent": quality.get("loss_percent", 0),
                "reachable": quality.get("reachable", True),
                "timestamp": time.time(),
                # Link traffic stats (from tc - actual delivered traffic)
                "tx_bytes_sec": link_traffic.get("tx_bytes_sec", 0),
                "tx_packets_sec": link_traffic.get("tx_packets_sec", 0),
                "dropped_sec": link_traffic.get("dropped_sec", 0),
            }

        write_metrics()
        time.sleep(PROBE_INTERVAL)

def write_metrics():
    """Write metrics to shared volume."""
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    metrics_file = METRICS_DIR / f"drone{DRONE_ID}.json"

    data = {
        "drone_id": DRONE_ID,
        "timestamp": time.time(),
        "position": state.positions.get(DRONE_ID, {}),
        "environment": state.environment,
        "topology": state.topology,
        "bandwidth_kbps": get_radio_bandwidth(),
        "probes": probe_results,
        "link_quality": {str(k): v for k, v in state.link_quality.items()},
        "link_overrides": {str(k): v for k, v in state.link_overrides.items()},
        "traffic": state.traffic_stats,
    }

    with open(metrics_file, "w") as f:
        json.dump(data, f)

# TCP/UDP probe servers
def start_tcp_server():
    """TCP server for probing."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", 9000))
    server.listen(5)
    while True:
        try:
            conn, _ = server.accept()
            conn.recv(64)
            conn.send(f"DRONE{DRONE_ID}_OK\n".encode())
            conn.close()
        except Exception:
            pass

def start_udp_server():
    """UDP server for probing."""
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("0.0.0.0", 9001))
    while True:
        try:
            data, addr = server.recvfrom(64)
            server.sendto(f"DRONE{DRONE_ID}_OK\n".encode(), addr)
        except Exception:
            pass

# HTTP API
class RadioHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

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

    def read_json(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length:
            return json.loads(self.rfile.read(content_length))
        return {}

    def do_GET(self):
        if self.path == "/status":
            self.send_json({
                "drone_id": DRONE_ID,
                "position": state.positions.get(DRONE_ID, {}),
                "environment": state.environment,
                "topology": state.topology,
                "bandwidth_kbps": get_radio_bandwidth(),
                "probes": probe_results,
                "link_quality": state.link_quality,
                "link_overrides": state.link_overrides,
            })
        elif self.path == "/config":
            self.send_json(CONFIG)
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/position":
            # Update this drone's position
            data = self.read_json()
            state.positions[DRONE_ID] = {
                "x": data.get("x", 0),
                "y": data.get("y", 0),
                "z": data.get("z", 0),
            }
            apply_link_rules()
            self.send_json({"ok": True, "position": state.positions[DRONE_ID]})

        elif self.path == "/environment":
            # Update environment profile
            data = self.read_json()
            profile = data.get("profile", "clear")
            if profile in CONFIG.get("environment", {}).get("profiles", {}):
                state.environment = profile
                setup_htb_root()  # Reconfigure bandwidth
                apply_link_rules()
                self.send_json({"ok": True, "environment": state.environment})
            else:
                self.send_json({"error": "unknown profile"}, 400)

        elif self.path == "/topology":
            # Update topology mode
            data = self.read_json()
            mode = data.get("mode", "mesh")
            if mode in ["mesh", "star"]:
                state.topology = mode
                apply_link_rules()
                self.send_json({"ok": True, "topology": state.topology})
            else:
                self.send_json({"error": "unknown topology"}, 400)

        elif self.path.startswith("/positions/"):
            # Update another drone's position (for coordinator)
            try:
                target_id = int(self.path.split("/")[2])
                data = self.read_json()
                state.positions[target_id] = {
                    "x": data.get("x", 0),
                    "y": data.get("y", 0),
                    "z": data.get("z", 0),
                }
                apply_link_rules()
                self.send_json({"ok": True, "position": state.positions[target_id]})
            except (ValueError, IndexError):
                self.send_json({"error": "invalid drone id"}, 400)

        elif self.path == "/link_override":
            # Set link quality override
            data = self.read_json()
            target_id = data.get("target")
            if target_id is None:
                self.send_json({"error": "target required"}, 400)
                return

            state.link_overrides[target_id] = {
                "extra_latency_ms": data.get("extra_latency_ms", 0),
                "extra_loss_percent": data.get("extra_loss_percent", 0),
                "partition": data.get("partition", False),
            }
            apply_link_rules()
            print(f"Link override set for target {target_id}: {state.link_overrides[target_id]}")
            self.send_json({"ok": True, "override": state.link_overrides[target_id]})

        else:
            self.send_json({"error": "not found"}, 404)

    def do_DELETE(self):
        if self.path.startswith("/link_override/"):
            # Clear link quality override
            try:
                target_id = int(self.path.split("/")[2])
                if target_id in state.link_overrides:
                    del state.link_overrides[target_id]
                    apply_link_rules()
                    print(f"Link override cleared for target {target_id}")
                self.send_json({"ok": True})
            except (ValueError, IndexError):
                self.send_json({"error": "invalid target id"}, 400)
        else:
            self.send_json({"error": "not found"}, 404)

def main():
    global MANET_INTERFACE
    MANET_INTERFACE = get_manet_interface()

    print(f"Enhanced Radio starting for drone {DRONE_ID}")
    print(f"MANET interface: {MANET_INTERFACE}")
    print(f"Topology: {state.topology}")
    print(f"Environment: {state.environment}")
    print(f"Bandwidth: {get_radio_bandwidth()} kbit/s")

    # Set up traffic control on the MANET interface
    setup_htb_root()
    apply_link_rules()

    # Set up iptables accounting for per-link traffic stats
    setup_iptables_accounting()

    # Start servers
    threading.Thread(target=start_tcp_server, daemon=True).start()
    threading.Thread(target=start_udp_server, daemon=True).start()
    threading.Thread(target=probe_loop, daemon=True).start()

    # Start HTTP API
    server = HTTPServer(("0.0.0.0", 8080), RadioHandler)
    print("Radio API listening on port 8080")
    server.serve_forever()

if __name__ == "__main__":
    main()
