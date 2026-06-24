import httpx
from backend.config import settings

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=10.0)
    return _client


async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
    _client = None


async def st_request(
    method: str,
    path: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    headers: dict | None = None,
    content: bytes | None = None,
    params: dict | None = None,
) -> httpx.Response:
    url = f"{base_url or settings.st_base_url}/{path.lstrip('/')}"
    merged = dict(headers or {})
    merged["X-API-Key"] = api_key or settings.st_api_key
    merged.pop("host", None)
    merged.pop("Host", None)
    return await get_client().request(
        method,
        url,
        headers=merged,
        content=content,
        params=params,
    )
