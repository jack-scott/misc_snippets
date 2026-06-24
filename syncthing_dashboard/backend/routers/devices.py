import ipaddress

from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend.services.st_client import st_request

router = APIRouter(prefix="/api/devices", tags=["devices"])


def _connectivity_tier(address: str, connected: bool) -> str:
    if not connected:
        return "offline"
    if address.startswith("relay://"):
        return "relay"
    try:
        host = address.split("://")[-1].rsplit(":", 1)[0].strip("[]")
        ip = ipaddress.ip_address(host)
        network = ipaddress.ip_network(settings.local_subnet, strict=False)
        return "local" if ip in network else "wan"
    except ValueError:
        return "wan"


async def _server_id() -> str:
    r = await st_request("GET", "/rest/system/status")
    return r.json()["myID"]


@router.get("")
async def list_devices():
    try:
        cfg_resp  = await st_request("GET", "/rest/config/devices")
        conn_resp = await st_request("GET", "/rest/system/connections")
        my_id     = await _server_id()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Syncthing unreachable: {e}")

    if cfg_resp.status_code != 200:
        raise HTTPException(status_code=cfg_resp.status_code, detail="Failed to fetch device config")
    if conn_resp.status_code != 200:
        raise HTTPException(status_code=conn_resp.status_code, detail="Failed to fetch connections")

    configured: list[dict] = cfg_resp.json()
    connections: dict = conn_resp.json().get("connections", {})

    result = []
    for device in configured:
        dev_id = device["deviceID"]
        if dev_id == my_id:
            continue  # skip server's own entry if it somehow got added
        conn = connections.get(dev_id, {})
        connected = conn.get("connected", False)
        address = conn.get("address", "")
        result.append({
            "deviceID": dev_id,
            "name": device.get("name", dev_id[:7]),
            "addresses": device.get("addresses", []),
            "connected": connected,
            "address": address,
            "connectivity": _connectivity_tier(address, connected),
            "clientVersion": conn.get("clientVersion", ""),
            "inBytesTotal": conn.get("inBytesTotal", 0),
            "outBytesTotal": conn.get("outBytesTotal", 0),
        })
    return result


@router.delete("/{device_id}")
async def remove_device(device_id: str):
    r = await st_request("DELETE", f"/rest/config/devices/{device_id}")
    if r.status_code not in (200, 204):
        raise HTTPException(status_code=r.status_code, detail=f"Syncthing returned {r.status_code}: {r.text}")
    return {"removed": device_id}
