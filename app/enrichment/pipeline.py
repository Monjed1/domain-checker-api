from __future__ import annotations

import asyncio

from app.enrichment.age import enrich_registration_age
from app.enrichment.backlinks import analyze_backlinks
from app.enrichment.dns_lookup import analyze_dns
from app.enrichment.registration import parse_registration
from app.enrichment.wayback import analyze_wayback
from app.lookup import LookupResult
from app.models import DomainAnalysis


async def build_domain_analysis(lookup: LookupResult) -> DomainAnalysis:
    is_registered = lookup.status.value == "registered"

    registration = parse_registration(
        is_registered=is_registered,
        rdap_payload=lookup.rdap_payload,
        whois_text=lookup.whois_text,
        whois_record=lookup.whois_record,
    )

    wayback_task = analyze_wayback(lookup.domain)
    dns_task = analyze_dns(lookup.domain)
    backlinks_task = analyze_backlinks(lookup.domain, is_registered=is_registered)

    wayback, dns, backlinks = await asyncio.gather(wayback_task, dns_task, backlinks_task)

    # Cross-signal: Wayback + current DNS
    if wayback.was_archived and wayback.snapshot_count >= 3:
        if dns.had_live_hosting or wayback.likely_real_business:
            dns = dns.model_copy(
                update={
                    "inferred_historical_hosting": True,
                    "note": dns.note
                    + " Wayback shows prior live use.",
                }
            )

    if wayback.risk_flags and dns.likely_parked:
        dns = dns.model_copy(
            update={"likely_spam_or_parked_history": True},
        )

    registration = enrich_registration_age(registration, wayback)

    return DomainAnalysis(
        registration=registration,
        wayback=wayback,
        backlinks=backlinks,
        dns=dns,
    )
