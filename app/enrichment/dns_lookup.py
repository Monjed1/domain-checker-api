from __future__ import annotations

import asyncio
import re

import dns.asyncresolver
import dns.exception

from app.models import DnsHistoryInfo

PARKING_NS_KEYWORDS = (
    "sedo",
    "bodis",
    "afternic",
    "parkingcrew",
    "hugedomains",
    "dan.com",
    "undeveloped",
    "parked",
    "above.com",
    "skenzo",
    "fabulous",
    "parklogic",
    "cashparking",
)

PARKING_TXT_KEYWORDS = ("sedo", "parking", "forsale", "domain for sale", "buydomains")
PARKING_CNAME_KEYWORDS = ("sedoparking", "parking", "parked", "afternic", "bodis")


async def analyze_dns(domain: str) -> DnsHistoryInfo:
    resolver = dns.asyncresolver.Resolver()
    resolver.lifetime = 8.0

    a_records: list[str] = []
    aaaa_records: list[str] = []
    mx_hosts: list[str] = []
    ns_hosts: list[str] = []
    txt_samples: list[str] = []
    cnames: list[str] = []
    errors: list[str] = []

    for qtype, collector in (
        ("A", lambda vals: a_records.extend(vals)),
        ("AAAA", lambda vals: aaaa_records.extend(vals)),
        ("MX", lambda vals: mx_hosts.extend(vals)),
        ("NS", lambda vals: ns_hosts.extend(vals)),
        ("TXT", lambda vals: txt_samples.extend(vals)),
        ("CNAME", lambda vals: cnames.extend(vals)),
    ):
        try:
            answers = await resolver.resolve(domain, qtype)
            strings = [_answer_to_str(qtype, r) for r in answers]
            collector([s for s in strings if s])
        except (dns.exception.DNSException, OSError) as exc:
            errors.append(f"{qtype}: {exc}")

    combined = " ".join(
        [*ns_hosts, *txt_samples, *cnames, *mx_hosts, *a_records]
    ).lower()

    is_parked = _detect_parking(combined, bool(mx_hosts), bool(a_records or aaaa_records))
    had_hosting = bool(a_records or aaaa_records or mx_hosts or cnames)
    had_email = bool(mx_hosts)

    return DnsHistoryInfo(
        resolves=had_hosting or bool(ns_hosts),
        a_records=a_records,
        aaaa_records=aaaa_records,
        mx_hosts=mx_hosts,
        ns_hosts=ns_hosts,
        txt_samples=txt_samples[:5],
        cnames=cnames,
        likely_parked=is_parked,
        had_live_hosting=had_hosting and not is_parked,
        had_email_setup=had_email,
        note=(
            "Live DNS only (no paid DNS-history API). Historical hosting inferred from Wayback when available."
        ),
        lookup_errors=errors,
    )


def _answer_to_str(qtype: str, record: dns.rdata.Rdata) -> str:
    if qtype == "MX":
        return str(record.exchange).rstrip(".").lower()
    if qtype in ("NS", "CNAME"):
        return str(record.target).rstrip(".").lower()
    if qtype == "TXT":
        txt = b"".join(record.strings).decode("utf-8", errors="replace")
        return txt[:200]
    return str(record).split()[-1]


def _detect_parking(blob: str, has_mx: bool, has_a: bool) -> bool:
    if any(k in blob for k in PARKING_NS_KEYWORDS):
        return True
    if any(k in blob for k in PARKING_TXT_KEYWORDS):
        return True
    if any(k in blob for k in PARKING_CNAME_KEYWORDS):
        return True
    if has_a and not has_mx and re.search(r"parking|forsale|sedo", blob):
        return True
    return False
