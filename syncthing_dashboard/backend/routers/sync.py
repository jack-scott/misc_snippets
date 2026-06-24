import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.st_client import st_request

router = APIRouter(prefix="/api/sync", tags=["sync"])


async def _browse_global(folder_id: str) -> dict[str, dict]:
    """Global directory tree — server receives drone's full index regardless of ignores."""
    r = await st_request("GET", "/rest/db/browse", params={"folder": folder_id, "levels": "1"})
    if r.status_code != 200:
        return {}
    result = {}
    for entry in (r.json() if isinstance(r.json(), list) else []):
        if entry.get("type") != "FILE_INFO_TYPE_DIRECTORY":
            continue
        children = entry.get("children") or []
        result[entry["name"]] = {
            "bytes": sum(c.get("size", 0) for c in children),
            "files": sum(1 for c in children if c.get("type") == "FILE_INFO_TYPE_FILE"),
        }
    return result


async def _need_by_date(folder_id: str) -> dict[str, int]:
    """
    Per-date bytes that the server still needs to download.
    db/need excludes ignored files, so 0 means either fully synced or not enabled.
    """
    need_per_date: dict[str, int] = {}
    try:
        r = await st_request(
            "GET", "/rest/db/need",
            params={"folder": folder_id, "page": 1, "perpage": 2000},
        )
        if r.status_code != 200:
            return need_per_date
        for f in r.json().get("files", []):
            parts = f.get("name", "").split("/", 1)
            if parts and parts[0]:
                date_key = parts[0]
                need_per_date[date_key] = need_per_date.get(date_key, 0) + f.get("size", 0)
    except Exception:
        pass
    return need_per_date


@router.get("/{folder_id}/dates")
async def get_dates(folder_id: str):
    # Enabled dates from server ignore patterns
    try:
        ignore_r = await st_request("GET", "/rest/db/ignores", params={"folder": folder_id})
        ignores = ignore_r.json().get("ignore", []) if ignore_r.status_code == 200 else []
    except Exception:
        ignores = []
    enabled_dates = {line[2:] for line in ignores if line.startswith("!/")}

    # Server has the drone's full index through Syncthing's index sharing — no tunnel needed
    global_dates = await _browse_global(folder_id)

    # Per-date bytes server still needs (only non-zero for enabled, not-yet-synced dates)
    need_per_date = await _need_by_date(folder_id)

    # Include dates enabled but not yet in the global index (pre-configured future dates)
    all_dates = sorted(set(global_dates.keys()) | enabled_dates, reverse=True)

    result = []
    for date in all_dates:
        g = global_dates.get(date, {"bytes": 0, "files": 0})
        global_bytes = g["bytes"]

        if date in enabled_dates and global_bytes > 0:
            # db/need is 0 for ignored files, so we only use it when date is enabled
            needed = need_per_date.get(date, 0)
            server_bytes = max(0, global_bytes - needed)
            progress = round(min(server_bytes / global_bytes * 100, 100.0), 1)
        else:
            server_bytes = 0
            progress = 0.0

        result.append({
            "date": date,
            "droneBytes": global_bytes,
            "droneFiles": g["files"],
            "serverBytes": server_bytes,
            "syncEnabled": date in enabled_dates,
            "progress": progress,
        })
    return result


class ToggleRequest(BaseModel):
    enabled: bool


class ToggleRangeRequest(BaseModel):
    dates: list[str]
    enabled: bool


async def _apply_dates(folder_id: str, dates: list[str], enabled: bool) -> list[str]:
    """Add or remove a set of dates from the server's ignore whitelist. Returns new ignore list."""
    try:
        r = await st_request("GET", "/rest/db/ignores", params={"folder": folder_id})
        current = r.json().get("ignore", ["*"]) if r.status_code == 200 else ["*"]
    except Exception:
        current = ["*"]

    active = {line[2:] for line in current if line.startswith("!/")}
    for date in dates:
        active.add(date) if enabled else active.discard(date)

    new_ignores = [f"!/{d}" for d in sorted(active)] + ["*"]
    await st_request(
        "POST", "/rest/db/ignores",
        params={"folder": folder_id},
        content=json.dumps({"ignore": new_ignores}).encode(),
        headers={"Content-Type": "application/json"},
    )
    return new_ignores


@router.put("/{folder_id}/dates")
async def toggle_date_range(folder_id: str, body: ToggleRangeRequest):
    if not body.dates:
        raise HTTPException(status_code=400, detail="dates list is empty")
    try:
        new_ignores = await _apply_dates(folder_id, body.dates, body.enabled)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to update ignores: {e}")
    return {"folder_id": folder_id, "dates": body.dates, "enabled": body.enabled, "ignore": new_ignores}


@router.put("/{folder_id}/date/{date}")
async def toggle_date(folder_id: str, date: str, body: ToggleRequest):
    try:
        await _apply_dates(folder_id, [date], body.enabled)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to update ignores: {e}")
    return {"folder_id": folder_id, "date": date, "enabled": body.enabled}
