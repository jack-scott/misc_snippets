#!/usr/bin/env python3
"""
One-time setup: pair all drone Syncthings with the server after docker-compose up.

Opens a temporary SSH tunnel to each drone to reach its Syncthing API, then:
  - Adds drone↔server to each other's device lists
  - Shares the organised folder both ways

Run from the syncthing_dashboard/ directory:
    python3 tools/init_drones.py
"""
import sys
import time
import socket
import subprocess
import requests

# ── Config ────────────────────────────────────────────────────────────────────

SERVER_URL     = "http://localhost:8384"
SERVER_API_KEY = "server-api-key-fleetserver01"
SERVER_NAME    = "fleet-server"

TEST_KEY_PATH  = "docker/keys/test_key"
SSH_USER       = "root"

DRONES = [
    {"name": "drone-alpha-1", "ssh_port": 2201, "api_key": "drone1-api-key-alpha001"},
    {"name": "drone-beta-2",  "ssh_port": 2202, "api_key": "drone2-api-key-beta002"},
    {"name": "drone-gamma-3", "ssh_port": 2203, "api_key": "drone3-api-key-gamma003"},
]

# Temporary tunnel ports — only used during this script
TUNNEL_BASE = 19001

# ── Helpers ───────────────────────────────────────────────────────────────────

def wait_for_api(label, url, api_key, timeout=120):
    headers = {"X-API-Key": api_key}
    print(f"  {label}: waiting", end="", flush=True)
    for _ in range(timeout):
        try:
            r = requests.get(f"{url}/rest/system/ping", headers=headers, timeout=2)
            if r.status_code == 200:
                print(" ready")
                return True
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(1)
    print(" TIMEOUT")
    return False


def wait_for_port(port, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.2)
    return False


def open_tunnel(ssh_port, local_port):
    proc = subprocess.Popen([
        "ssh", "-N",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ConnectTimeout=5",
        "-i", TEST_KEY_PATH,
        "-p", str(ssh_port),
        "-L", f"{local_port}:127.0.0.1:8384",
        f"{SSH_USER}@127.0.0.1",
    ], stderr=subprocess.DEVNULL)
    if not wait_for_port(local_port, timeout=10):
        proc.terminate()
        raise RuntimeError(f"Tunnel to SSH port {ssh_port} did not open")
    return proc


def get_device_id(url, api_key):
    r = requests.get(f"{url}/rest/system/status",
                     headers={"X-API-Key": api_key}, timeout=5)
    return r.json()["myID"]


def add_device(url, api_key, device_id, name, addresses=None):
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    existing = {d["deviceID"] for d in
                requests.get(f"{url}/rest/config/devices", headers=headers, timeout=5).json()}
    if device_id in existing:
        print(f"    already paired: {name}")
        return
    r = requests.post(f"{url}/rest/config/devices",
                      json={"deviceID": device_id, "name": name,
                            "addresses": addresses or ["dynamic"]},
                      headers=headers, timeout=5)
    print(f"    added {name}: HTTP {r.status_code}")


def share_folder(url, api_key, folder_id, device_id):
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    r = requests.get(f"{url}/rest/config/folders/{folder_id}", headers=headers, timeout=5)
    if r.status_code != 200:
        print(f"    folder '{folder_id}' not found — skipping")
        return
    folder = r.json()
    if any(d["deviceID"] == device_id for d in folder.get("devices", [])):
        print(f"    {folder_id} already shared")
        return
    folder["devices"].append({"deviceID": device_id, "introducedBy": "", "encryptionPassword": ""})
    r = requests.put(f"{url}/rest/config/folders/{folder_id}",
                     json=folder, headers=headers, timeout=5)
    print(f"    shared {folder_id}: HTTP {r.status_code}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Waiting for server Syncthing...")
    if not wait_for_api("server", SERVER_URL, SERVER_API_KEY):
        sys.exit(1)

    server_id = get_device_id(SERVER_URL, SERVER_API_KEY)
    print(f"Server device ID: {server_id}\n")

    for i, drone in enumerate(DRONES):
        tunnel_port = TUNNEL_BASE + i
        print(f"── {drone['name']} (SSH :{ drone['ssh_port']}) ──")

        # Open SSH tunnel to this drone's Syncthing
        print(f"  opening tunnel localhost:{tunnel_port} → drone SSH :{drone['ssh_port']}...")
        try:
            proc = open_tunnel(drone["ssh_port"], tunnel_port)
        except RuntimeError as e:
            print(f"  FAILED: {e}")
            continue

        drone_url = f"http://127.0.0.1:{tunnel_port}"
        try:
            if not wait_for_api(drone["name"], drone_url, drone["api_key"], timeout=20):
                continue

            drone_id = get_device_id(drone_url, drone["api_key"])
            print(f"  device ID: {drone_id}")

            # Server knows about drone (point drone at server's sync port)
            add_device(SERVER_URL, SERVER_API_KEY, drone_id, drone["name"])
            # Drone knows about server (direct Docker network address)
            add_device(drone_url, drone["api_key"], server_id, SERVER_NAME,
                       addresses=["tcp://server:22000"])

            # Share organised folder both ways
            share_folder(SERVER_URL, SERVER_API_KEY, "organised", drone_id)
            share_folder(drone_url,  drone["api_key"],  "organised", server_id)

        finally:
            proc.terminate()
            proc.wait()
            print(f"  tunnel closed")

        print()

    print("Done. All reachable drones paired with server.")


if __name__ == "__main__":
    main()
