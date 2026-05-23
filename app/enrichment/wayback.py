from __future__ import annotations

import re

import httpx

from app.config import settings
from app.models import RiskLevel, WaybackInfo

CDX_URL = "https://web.archive.org/cdx/search/cdx"

_RISK_PATTERNS: dict[str, re.Pattern[str]] = {
    "adult": re.compile(
        r"\b(porn|xxx|adult|escort|webcam|sex-|sexcam)\b", re.IGNORECASE
    ),
    "gambling": re.compile(
        r"\b(casino|poker|betting|sportsbook|slot-|jackpot|baccarat)\b", re.IGNORECASE
    ),
    "pharma": re.compile(
        r"\b(viagra|cialis|pharmacy|pillshop|rx-|prescription)\b", re.IGNORECASE
    ),
    "spam": re.compile(
        r"\b(payday|replica|counterfeit|seo-service|link-building|casino-bonus)\b",
        re.IGNORECASE,
    ),
}

_BUSINESS_PATH = re.compile(
    r"/(about|contact|services|products|company|team|pricing)(/|$)", re.IGNORECASE
)


async def analyze_wayback(domain: str) -> WaybackInfo:
    """Query Internet Archive public CDX index (no API key)."""
    params = {
        "url": f"{domain}/*",
        "output": "json",
        "fl": "timestamp,original,statuscode,mimetype",
        "filter": "statuscode:200",
        "collapse": "urlkey",
        "limit": 80,
    }

    try:
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
        ) as client:
            response = await client.get(CDX_URL, params=params)
            response.raise_for_status()
            rows = response.json()
    except httpx.HTTPError as exc:
        return WaybackInfo(
            was_archived=False,
            source="internet_archive_cdx",
            note=f"Wayback CDX lookup failed: {exc}",
        )

    if not rows or len(rows) < 2:
        return WaybackInfo(
            was_archived=False,
            source="internet_archive_cdx",
            note="No archived snapshots found in Wayback Machine.",
        )

    headers = rows[0]
    data_rows = rows[1:]
    snapshots = [_row_to_dict(headers, row) for row in data_rows]

    timestamps = [s["timestamp"] for s in snapshots if s.get("timestamp")]
    first_seen = _format_ts(min(timestamps)) if timestamps else None
    last_seen = _format_ts(max(timestamps)) if timestamps else None
    originals = [s.get("original", "") for s in snapshots]

    risk_flags = _detect_risks(" ".join(originals))
    had_business_paths = any(_BUSINESS_PATH.search(url) for url in originals)
    html_snapshots = sum(
        1 for s in snapshots if (s.get("mimetype") or "").startswith("text/html")
    )

    likely_real_business = (
        len(snapshots) >= 5
        and html_snapshots >= 3
        and (had_business_paths or len(timestamps) >= 3)
        and not risk_flags
    )

    return WaybackInfo(
        was_archived=True,
        snapshot_count=len(snapshots),
        first_seen=first_seen,
        last_seen=last_seen,
        likely_real_business=likely_real_business,
        risk_flags=risk_flags,
        risk_level=_overall_risk(risk_flags),
        sample_urls=originals[:8],
        source="internet_archive_cdx",
        note="Heuristic analysis from public CDX metadata only (not full page content).",
    )


def _row_to_dict(headers: list[str], row: list[str]) -> dict[str, str]:
    return {headers[i]: row[i] for i in range(min(len(headers), len(row)))}


def _format_ts(ts: str) -> str:
    if len(ts) >= 8:
        return f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}"
    return ts


def _detect_risks(blob: str) -> list[str]:
    return [name for name, pattern in _RISK_PATTERNS.items() if pattern.search(blob)]


def _overall_risk(flags: list[str]) -> RiskLevel:
    if not flags:
        return RiskLevel.NONE
    if len(flags) >= 2:
        return RiskLevel.HIGH
    return RiskLevel.MEDIUM
