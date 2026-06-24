import json
import re
import socket
import subprocess
import time

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import settings
from backend.services import ssh as ssh_svc
from backend.services.st_client import st_request

router = APIRouter(prefix="/api/provision", tags=["provision"])


def _folder_id(name: str) -> str:
    clean = re.sub(r'[^a-z0-9-]+', '-', name.lower()).strip('-')
    return f"organised-{clean or 'drone'}"


def _wait_for_port(port: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.2)
    return False


async def _open_temp_tunnel(host: str, ssh_port: int, key_path: str) -> tuple[int, subprocess.Popen]:
    used = {t["local_port"] for t in ssh_svc.get_all_tunnels()}
    port = settings.tunnel_port_start
    while port in used:
        port += 1

    proc = subprocess.Popen(
        [
            "ssh", "-N",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "ConnectTimeout=5",
            "-i", key_path,
            "-p", str(ssh_port),
            "-L", f"{port}:127.0.0.1:8384",
            f"root@{host}",
        ],
        stderr=subprocess.DEVNULL,
    )
    if not _wait_for_port(port, timeout=10.0):
        proc.terminate()
        proc.wait()
        raise RuntimeError(f"Temp tunnel to {host}:{ssh_port} did not open")
    return port, proc


class AddDroneRequest(BaseModel):
    name: str
    host: str
    ssh_port: int = 22
    key_path: str | None = None


@router.post("/add")
async def add_drone(body: AddDroneRequest):
    key = body.key_path or settings.ssh_key_path
    folder_id = _folder_id(body.name)
    sanitized = folder_id[len("organised-"):]

    # 1. Get drone API key via SSH
    try:
        api_key = await ssh_svc.run_ssh_command(
            body.host, body.ssh_port, key,
            "python3 -c \"import xml.etree.ElementTree as ET; "
            "print(ET.parse('/config/config.xml').find('.//gui/apikey').text)\"",
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"SSH failed: {e}")
    if not api_key:
        raise HTTPException(status_code=502, detail="Could not read API key from drone config.xml")

    # 2. Get drone device ID via temp tunnel
    try:
        local_port, proc = await _open_temp_tunnel(body.host, body.ssh_port, key)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"http://127.0.0.1:{local_port}/rest/system/status",
                headers={"X-API-Key": api_key},
            )
        drone_id = r.json()["myID"]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach drone Syncthing: {e}")
    finally:
        proc.terminate()
        proc.wait()

    # 3. Get server device ID
    try:
        sr = await st_request("GET", "/rest/system/status")
        server_id = sr.json()["myID"]
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not get server ID: {e}")

    # 4. Add drone to server device list
    try:
        cfg_r = await st_request("GET", "/rest/config/devices")
        if drone_id not in {d["deviceID"] for d in cfg_r.json()}:
            await st_request(
                "POST", "/rest/config/devices",
                content=json.dumps({"deviceID": drone_id, "name": body.name, "addresses": ["dynamic"]}).encode(),
                headers={"Content-Type": "application/json"},
            )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to add drone to server: {e}")

    # 5. Drone-side config via temp tunnel
    try:
        local_port, proc = await _open_temp_tunnel(body.host, body.ssh_port, key)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            hdrs_json = {"X-API-Key": api_key, "Content-Type": "application/json"}
            base = f"http://127.0.0.1:{local_port}"

            # Add server to drone device list
            existing_r = await client.get(f"{base}/rest/config/devices", headers={"X-API-Key": api_key})
            if server_id not in {d["deviceID"] for d in existing_r.json()}:
                await client.post(
                    f"{base}/rest/config/devices",
                    json={"deviceID": server_id, "name": "fleet-server", "addresses": ["tcp://server:22000"]},
                    headers=hdrs_json,
                )

            # Remove old shared 'organised' folder to avoid path conflict
            old_r = await client.get(f"{base}/rest/config/folders/organised", headers={"X-API-Key": api_key})
            if old_r.status_code == 200:
                await client.delete(f"{base}/rest/config/folders/organised", headers={"X-API-Key": api_key})

            # Create per-drone folder if not already present (idempotent re-provision)
            check_r = await client.get(f"{base}/rest/config/folders/{folder_id}", headers={"X-API-Key": api_key})
            if check_r.status_code != 200:
                await client.post(
                    f"{base}/rest/config/folders",
                    json={
                        "id": folder_id,
                        "label": body.name,
                        "path": "/data/organised",
                        "type": "sendonly",
                        "devices": [{"deviceID": server_id, "introducedBy": "", "encryptionPassword": ""}],
                        "rescanIntervalS": 30,
                    },
                    headers=hdrs_json,
                )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Drone-side config failed: {e}")
    finally:
        proc.terminate()
        proc.wait()

    # 6. Server-side folder (receiveOnly, one per drone)
    try:
        folder_list_r = await st_request("GET", "/rest/config/folders")
        existing_ids = {f["id"] for f in folder_list_r.json()}
        if folder_id not in existing_ids:
            await st_request(
                "POST", "/rest/config/folders",
                content=json.dumps({
                    "id": folder_id,
                    "label": body.name,
                    "path": f"/data/organised/{sanitized}",
                    "type": "receiveOnly",
                    "devices": [{"deviceID": drone_id, "introducedBy": "", "encryptionPassword": ""}],
                    "rescanIntervalS": 30,
                }).encode(),
                headers={"Content-Type": "application/json"},
            )
        # Default: ignore everything — operator enables per-date via the UI
        await st_request(
            "POST", "/rest/db/ignores",
            params={"folder": folder_id},
            content=json.dumps({"ignore": ["*"]}).encode(),
            headers={"Content-Type": "application/json"},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Server folder setup failed: {e}")

    return {
        "device_id": drone_id,
        "name": body.name,
        "folder_id": folder_id,
        "api_key": api_key,
        "host": body.host,
        "ssh_port": body.ssh_port,
        "key_path": key,
    }
