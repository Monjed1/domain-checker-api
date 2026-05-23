from __future__ import annotations

import re
from typing import Any

from app.enrichment.wayback_client import fetch_availability, fetch_cdx
from app.models import RiskLevel, WaybackInfo

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
    rows, error = await fetch_cdx(domain)

    if error and "429" in error:
        fallback = await _availability_fallback(domain, error)
        if fallback is not None:
            return fallback

    if error:
        is_rate_limited = "429" in error or "Rate limited" in error
        return WaybackInfo(
            was_archived=False,
            lookup_status="rate_limited" if is_rate_limited else "error",
            rate_limited=is_rate_limited,
            source="internet_archive_cdx",
            note=(
                f"Wayback lookup failed: {error}. "
                "Wait a few minutes, increase WAYBACK_MIN_INTERVAL_SECONDS, "
                "or check fewer domains per request."
            ),
        )

    if not rows or len(rows) < 2:
        return WaybackInfo(
            was_archived=False,
            lookup_status="not_found",
            source="internet_archive_cdx",
            note="No archived snapshots found in Wayback Machine.",
        )

    return _build_from_cdx_rows(rows)


async def _availability_fallback(domain: str, cdx_error: str) -> WaybackInfo | None:
    data, avail_error = await fetch_availability(domain)
    if avail_error or not isinstance(data, dict):
        return None

    archived = data.get("archived_snapshots") or {}
    closest = archived.get("closest") if isinstance(archived, dict) else None
    if not isinstance(closest, dict) or not closest.get("available"):
        return WaybackInfo(
            was_archived=False,
            lookup_status="not_found",
            source="internet_archive_availability",
            note=(
                "CDX rate-limited; availability API shows no snapshots. "
                f"CDX error: {cdx_error}"
            ),
        )

    timestamp = str(closest.get("timestamp", ""))
    first_seen = _format_ts(timestamp) if timestamp else None

    return WaybackInfo(
        was_archived=True,
        snapshot_count=1,
        first_seen=first_seen,
        last_seen=first_seen,
        likely_real_business=False,
        risk_flags=[],
        risk_level=RiskLevel.NONE,
        sample_urls=[str(closest.get("url", ""))] if closest.get("url") else [],
        lookup_status="partial",
        source="internet_archive_availability",
        note=(
            "CDX rate-limited (429); used lightweight availability API. "
            "Counts and risk analysis may be incomplete — retry later for full CDX data."
        ),
    )


def _build_from_cdx_rows(rows: list[Any]) -> WaybackInfo:
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
        lookup_status="ok",
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
