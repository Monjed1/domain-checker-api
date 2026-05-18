from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
import tldextract
import whois

from app.config import settings
from app.models import AvailabilityStatus, DomainResult

IANA_BOOTSTRAP_URL = settings.rdap_bootstrap_url

# WHOIS text patterns that indicate an unregistered / available name (registry-specific).
AVAILABLE_PATTERNS = re.compile(
    r"(no match|not found|no entries found|no data found|status:\s*free|"
    r"domain not found|no such domain|not registered|no object found|"
    r"nothing found|domain name not known|no information available|"
    r"is free|available for registration|no matching record|"
    r"the queried object does not exist|object does not exist|"
    r"domain you requested is not known|no whois server|not been registered)",
    re.IGNORECASE,
)

# WHOIS patterns when the name exists but cannot be registered.
UNAVAILABLE_PATTERNS = re.compile(
    r"(reserved|prohibited|restricted|not available for registration|"
    r"registry reserved|premium domain|blocked|invalid domain|"
    r"cannot be registered|registration not allowed)",
    re.IGNORECASE,
)

REGISTERED_PATTERNS = re.compile(
    r"(creation date|created on|registered on|registry expiry|"
    r"expir(y|ation) date|registrar:|domain status:|name server:)",
    re.IGNORECASE,
)


@dataclass
class _RdapServer:
    base_url: str


class DomainChecker:
    def __init__(self) -> None:
        self._bootstrap: dict[str, list[_RdapServer]] | None = None
        self._bootstrap_lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_checks)

    async def check_many(self, domains: list[str]) -> list[DomainResult]:
        unique = list(dict.fromkeys(self._normalize(d) for d in domains))
        tasks = [self._check_one(domain) for domain in unique]
        return list(await asyncio.gather(*tasks))

    async def _check_one(self, domain: str) -> DomainResult:
        async with self._semaphore:
            rdap_result = await self._check_rdap(domain)
            if rdap_result.status != AvailabilityStatus.UNKNOWN:
                return rdap_result

            whois_result = await asyncio.to_thread(self._check_whois, domain)
            return whois_result

    def _normalize(self, domain: str) -> str:
        domain = domain.strip().lower()
        domain = domain.removeprefix("http://").removeprefix("https://")
        domain = domain.split("/")[0].split("?")[0]
        if domain.startswith("www."):
            domain = domain[4:]
        return domain

    async def _load_bootstrap(self) -> dict[str, list[_RdapServer]]:
        async with self._bootstrap_lock:
            if self._bootstrap is not None:
                return self._bootstrap

            async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
                response = await client.get(IANA_BOOTSTRAP_URL)
                response.raise_for_status()
                data = response.json()

            mapping: dict[str, list[_RdapServer]] = {}
            for service in data.get("services", []):
                tlds, urls = service[0], service[1]
                servers = [_RdapServer(base_url=url.rstrip("/")) for url in urls]
                for tld in tlds:
                    key = tld.lower().lstrip(".")
                    mapping.setdefault(key, []).extend(servers)

            self._bootstrap = mapping
            return mapping

    def _tld(self, domain: str) -> str:
        extracted = tldextract.extract(domain)
        if not extracted.suffix:
            return ""
        return extracted.suffix.lower()

    async def _check_rdap(self, domain: str) -> DomainResult:
        tld = self._tld(domain)
        if not tld:
            return DomainResult(
                domain=domain,
                status=AvailabilityStatus.UNKNOWN,
                available=False,
                method="rdap",
                message="Invalid or unsupported domain format",
            )

        try:
            bootstrap = await self._load_bootstrap()
        except Exception as exc:
            return DomainResult(
                domain=domain,
                status=AvailabilityStatus.UNKNOWN,
                available=False,
                method="rdap",
                message=f"RDAP bootstrap failed: {exc}",
            )

        servers = bootstrap.get(tld, [])
        if not servers:
            return DomainResult(
                domain=domain,
                status=AvailabilityStatus.UNKNOWN,
                available=False,
                method="rdap",
                message=f"No RDAP server found for .{tld}",
            )

        last_error: str | None = None
        async with httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
            headers={"Accept": "application/rdap+json, application/json"},
        ) as client:
            for server in servers:
                url = f"{server.base_url}/domain/{domain}"
                try:
                    response = await client.get(url)
                except httpx.HTTPError as exc:
                    last_error = str(exc)
                    continue

                if response.status_code == 404:
                    body_text = response.text.lower()
                    if UNAVAILABLE_PATTERNS.search(body_text):
                        return DomainResult(
                            domain=domain,
                            status=AvailabilityStatus.UNAVAILABLE,
                            available=False,
                            method="rdap",
                            message="Domain is not registered but not available for registration",
                        )
                    return DomainResult(
                        domain=domain,
                        status=AvailabilityStatus.AVAILABLE,
                        available=True,
                        method="rdap",
                        message="Domain is not registered (RDAP 404)",
                    )

                if response.status_code == 200:
                    payload = response.json()
                    registrar, expiry = _parse_rdap_registration(payload)
                    return DomainResult(
                        domain=domain,
                        status=AvailabilityStatus.REGISTERED,
                        available=False,
                        method="rdap",
                        registrar=registrar,
                        expiry_date=expiry,
                        message="Domain is registered",
                    )

                if response.status_code in (301, 302, 307, 308):
                    continue

                last_error = f"RDAP HTTP {response.status_code}"

        return DomainResult(
            domain=domain,
            status=AvailabilityStatus.UNKNOWN,
            available=False,
            method="rdap",
            message=last_error or "RDAP lookup inconclusive",
        )

    def _check_whois(self, domain: str) -> DomainResult:
        try:
            record = whois.whois(domain)
        except Exception as exc:
            text = str(exc).lower()
            if AVAILABLE_PATTERNS.search(text):
                return DomainResult(
                    domain=domain,
                    status=AvailabilityStatus.AVAILABLE,
                    available=True,
                    method="whois",
                    message="Domain appears available (WHOIS)",
                )
            return DomainResult(
                domain=domain,
                status=AvailabilityStatus.UNKNOWN,
                available=False,
                method="whois",
                message=f"WHOIS error: {exc}",
            )

        raw_text = _whois_to_text(record)
        if UNAVAILABLE_PATTERNS.search(raw_text):
            return DomainResult(
                domain=domain,
                status=AvailabilityStatus.UNAVAILABLE,
                available=False,
                method="whois",
                message="Domain is reserved or restricted",
            )

        if _is_whois_registered(record, raw_text):
            registrar = _first_str(_record_field(record, "registrar"))
            expiry = _format_date(_record_field(record, "expiration_date"))
            return DomainResult(
                domain=domain,
                status=AvailabilityStatus.REGISTERED,
                available=False,
                method="whois",
                registrar=registrar,
                expiry_date=expiry,
                message="Domain is registered",
            )

        if AVAILABLE_PATTERNS.search(raw_text):
            return DomainResult(
                domain=domain,
                status=AvailabilityStatus.AVAILABLE,
                available=True,
                method="whois",
                message="Domain appears available (WHOIS)",
            )

        return DomainResult(
            domain=domain,
            status=AvailabilityStatus.UNKNOWN,
            available=False,
            method="whois",
            message="WHOIS lookup inconclusive",
        )


def _parse_rdap_registration(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    registrar: str | None = None
    expiry: str | None = None

    for event in payload.get("events", []):
        action = (event.get("eventAction") or "").lower()
        if action in ("expiration", "registrar expiration"):
            expiry = event.get("eventDate")
            if expiry and "T" in expiry:
                expiry = expiry.split("T")[0]

    for entity in payload.get("entities", []):
        roles = [r.lower() for r in entity.get("roles", [])]
        if "registrar" in roles:
            vcard = entity.get("vcardArray")
            if isinstance(vcard, list) and len(vcard) > 1:
                for row in vcard[1]:
                    if isinstance(row, list) and len(row) >= 4 and row[0] == "fn":
                        registrar = str(row[3])
                        break
            if not registrar:
                registrar = entity.get("handle")

    return registrar, expiry


def _whois_to_text(record: Any) -> str:
    if record is None:
        return ""
    if isinstance(record, str):
        return record
    if hasattr(record, "text") and record.text:
        if isinstance(record.text, list):
            return "\n".join(record.text)
        return str(record.text)
    try:
        return str(record)
    except Exception:
        return ""


def _is_whois_registered(record: Any, raw_text: str) -> bool:
    if record is None:
        return False

    for field in ("domain_name", "creation_date", "expiration_date", "registrar"):
        if _record_field(record, field):
            return True

    if REGISTERED_PATTERNS.search(raw_text):
        return True

    status = _record_field(record, "status")
    if status:
        return True

    return False


def _record_field(record: Any, name: str) -> Any:
    if isinstance(record, dict):
        return record.get(name)
    return getattr(record, name, None)


def _first_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        value = value[0] if value else None
    return str(value) if value else None


def _format_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    return str(value) if value else None


checker = DomainChecker()
