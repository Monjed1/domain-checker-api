from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.config import settings

CDX_URL = "https://web.archive.org/cdx/search/cdx"
AVAILABILITY_URL = "https://archive.org/wayback/available"

_HEADERS = {
    "User-Agent": "DomainCheckerAPI/2.0 (domain research)",
    "Accept": "application/json",
}

_wayback_gate = asyncio.Lock()
_last_wayback_at: float = 0.0
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


async def _wait_turn() -> None:
    global _last_wayback_at
    async with _wayback_gate:
        now = time.monotonic()
        wait = settings.wayback_min_interval_seconds - (now - _last_wayback_at)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_wayback_at = time.monotonic()


def _cache_get(key: str) -> dict[str, Any] | None:
    entry = _cache.get(key)
    if not entry:
        return None
    cached_at, payload = entry
    if time.monotonic() - cached_at > settings.wayback_cache_ttl_seconds:
        _cache.pop(key, None)
        return None
    return payload


def _cache_set(key: str, payload: dict[str, Any]) -> None:
    _cache[key] = (time.monotonic(), payload)
    if len(_cache) > 500:
        oldest = min(_cache, key=lambda k: _cache[k][0])
        _cache.pop(oldest, None)


def _retry_after_seconds(response: httpx.Response) -> float | None:
    header = response.headers.get("Retry-After")
    if not header:
        return None
    try:
        return float(header)
    except ValueError:
        return None


async def fetch_cdx(domain: str) -> tuple[list | None, str | None]:
    cache_key = f"cdx:{domain}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached.get("rows"), cached.get("error")

    params = {
        "url": f"{domain}/*",
        "output": "json",
        "fl": "timestamp,original,statuscode,mimetype",
        "filter": "statuscode:200",
        "collapse": "urlkey",
        "limit": settings.wayback_cdx_limit,
    }

    rows, error = await _request_json(CDX_URL, params)
    if rows is not None and error is None:
        _cache_set(cache_key, {"rows": rows, "error": None})
    return rows, error


async def fetch_availability(domain: str) -> tuple[dict[str, Any] | None, str | None]:
    cache_key = f"avail:{domain}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached.get("data"), cached.get("error")

    data, error = await _request_json(AVAILABILITY_URL, {"url": domain})
    if data is not None and error is None:
        _cache_set(cache_key, {"data": data, "error": None})
    return data, error


async def _request_json(
    url: str,
    params: dict[str, str | int],
) -> tuple[Any | None, str | None]:
    last_error: str | None = None

    for attempt in range(settings.wayback_max_retries + 1):
        await _wait_turn()

        try:
            async with httpx.AsyncClient(
                timeout=settings.request_timeout_seconds,
                follow_redirects=True,
                headers=_HEADERS,
            ) as client:
                response = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            last_error = str(exc)
            if attempt < settings.wayback_max_retries:
                await asyncio.sleep(settings.wayback_retry_base_seconds * (2**attempt))
            continue

        if response.status_code == 429:
            retry_after = _retry_after_seconds(response) or (
                settings.wayback_retry_base_seconds * (2**attempt)
            )
            last_error = "Rate limited by Internet Archive (HTTP 429)"
            if attempt < settings.wayback_max_retries:
                await asyncio.sleep(min(retry_after, 90.0))
                continue
            return None, last_error

        if response.status_code in (502, 503, 504):
            last_error = f"Internet Archive unavailable (HTTP {response.status_code})"
            if attempt < settings.wayback_max_retries:
                await asyncio.sleep(settings.wayback_retry_base_seconds * (2**attempt))
                continue
            return None, last_error

        if response.status_code >= 400:
            return None, f"HTTP {response.status_code}: {response.text[:200]}"

        try:
            return response.json(), None
        except ValueError:
            return None, "Invalid JSON from Internet Archive"

    return None, last_error
