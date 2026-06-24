from fastapi import APIRouter, Request, Response
from backend.services.st_client import st_request

router = APIRouter(prefix="/api/syncthing", tags=["syncthing"])

_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(path: str, request: Request) -> Response:
    upstream = await st_request(
        request.method,
        path,
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
