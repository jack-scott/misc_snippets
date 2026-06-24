import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services.st_client import st_request

router = APIRouter(prefix="/api/folders", tags=["folders"])


async def _browse_organised(base_url: str | None = None, api_key: str | None = None) -> list[dict]:
    r = await st_request(
        "GET",
        "/rest/db/browse",
        base_url=base_url,
        api_key=api_key,
        params={"folder": "organised", "levels": "1"},
    )
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail="Failed to browse organised folder")

    entries = r.json()
    result = []
    for entry in entries:
        if entry.get("type") != "FILE_INFO_TYPE_DIRECTORY":
            continue
        children = entry.get("children") or []
        files = [c for c in children if c.get("type") == "FILE_INFO_TYPE_FILE"]
        result.append({
            "name": entry["name"],
            "modTime": entry.get("modTime", ""),
            "sizeBytes": sum(f.get("size", 0) for f in files),
            "files": len(files),
        })
    result.sort(key=lambda d: d["name"], reverse=True)
    return result


@router.get("")
async def list_folders():
    return await _browse_organised()


class SetIgnoresRequest(BaseModel):
    dates: list[str]
    folder_id: str = "organised"


@router.put("/ignores")
async def set_ignores(body: SetIgnoresRequest):
    if body.dates:
        lines = [f"!/{d}" for d in sorted(body.dates)] + ["*"]
    else:
        lines = ["*"]

    r = await st_request(
        "POST",
        "/rest/db/ignores",
        content=json.dumps({"ignore": lines}).encode(),
        headers={"Content-Type": "application/json"},
        params={"folder": body.folder_id},
    )
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=r.status_code, detail=f"Failed to set ignores: {r.text}")
    return {"folder": body.folder_id, "ignore": lines}


@router.get("/ignores")
async def get_ignores(folder_id: str = "organised"):
    r = await st_request("GET", "/rest/db/ignores", params={"folder": folder_id})
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail="Failed to get ignores")
    data = r.json()
    lines = data.get("ignore") or []
    selected = [ln.lstrip("!/") for ln in lines if ln.startswith("!/")]
    return {"folder": folder_id, "ignore": lines, "selected_dates": selected}
