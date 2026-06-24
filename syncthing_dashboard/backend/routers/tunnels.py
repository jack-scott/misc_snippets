from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from backend.services import ssh as ssh_svc
from backend.services.st_client import st_request

router = APIRouter(prefix="/api/tunnel", tags=["tunnels"])

_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}


class OpenRequest(BaseModel):
    name: str
    host: str
    ssh_port: int
    api_key: str = ""
    key_path: str | None = None


class CloseRequest(BaseModel):
    name: str


@router.post("/open")
async def open_tunnel(body: OpenRequest):
    key = body.key_path or ssh_svc.key_path_for(body.name)
    try:
        tunnel = ssh_svc.open_tunnel(body.name, body.host, body.ssh_port, key, body.api_key)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {
        "name": tunnel.name,
        "local_port": tunnel.local_port,
        "host": tunnel.host,
        "ssh_port": tunnel.ssh_port,
    }


@router.post("/close")
async def close_tunnel(body: CloseRequest):
    closed = ssh_svc.close_tunnel(body.name)
    if not closed:
        raise HTTPException(status_code=404, detail=f"No tunnel named '{body.name}'")
    return {"closed": body.name}


@router.get("/status")
async def tunnel_status():
    return ssh_svc.get_all_tunnels()


@router.api_route("/{name}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_through_tunnel(name: str, path: str, request: Request) -> Response:
    tunnel = ssh_svc.get_tunnel(name)
    if tunnel is None:
        raise HTTPException(status_code=404, detail=f"No open tunnel for '{name}'")

    base_url = f"http://127.0.0.1:{tunnel.local_port}"
    upstream = await st_request(
        request.method,
        path,
        base_url=base_url,
        api_key=tunnel.api_key or None,
        headers=dict(request.headers),
        content=await request.body(),
        params=dict(request.query_params),
    )
    headers = {
        k: v for k, v in upstream.headers.items()
        if k.lower() not in _HOP_BY_HOP
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=headers,
        media_type=upstream.headers.get("content-type"),
    )
