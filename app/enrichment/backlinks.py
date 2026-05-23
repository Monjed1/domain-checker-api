from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.models import BacklinkInfo

# Without Ahrefs/Moz/Majestic APIs, we only probe the live homepage (if any).
_EXTERNAL_LINK = re.compile(
    r'<a\s+[^>]*href=["\'](https?://[^"\']+)["\']',
    re.IGNORECASE,
)


async def analyze_backlinks(domain: str, *, is_registered: bool) -> BacklinkInfo:
    if not is_registered:
        return BacklinkInfo(
            supported=False,
            note="Domain is not registered — no live site to probe for backlinks.",
        )

    for url in (f"https://{domain}", f"http://{domain}"):
        probe = await _probe_homepage(url, domain)
        if probe is not None:
            return probe

    return BacklinkInfo(
        supported=False,
        note=(
            "Backlink index data requires search-engine or SEO-provider APIs. "
            "Protocol-only mode cannot list domains linking to this name. "
            "Homepage probe also failed (no live HTTP site)."
        ),
    )


async def _probe_homepage(url: str, domain: str) -> BacklinkInfo | None:
    try:
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "DomainChecker/1.0 (homepage-probe)"},
        ) as client:
            response = await client.get(url)
    except httpx.HTTPError:
        return None

    if response.status_code >= 400:
        return None

    html = response.text[:200_000]
    hrefs = _EXTERNAL_LINK.findall(html)
    external_domains: set[str] = set()

    for href in hrefs:
        parsed = urlparse(href)
        host = (parsed.hostname or "").lower()
        if not host or host == domain or host.endswith(f".{domain}"):
            continue
        external_domains.add(host)

    # Outbound links on homepage ≠ backlinks TO domain; be explicit.
    return BacklinkInfo(
        supported=True,
        method="homepage_outbound_probe",
        referring_domains_count=len(external_domains),
        referring_domains_sample=sorted(external_domains)[:15],
        note=(
            "NOT a real backlink index. Shows external domains linked FROM the homepage only. "
            "Inbound backlink data is unavailable without third-party SEO APIs."
        ),
    )
