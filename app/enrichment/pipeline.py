from __future__ import annotations

import asyncio

from app.enrichment.age import enrich_registration_age
from app.enrichment.backlinks import analyze_backlinks
from app.enrichment.dns_lookup import analyze_dns
from app.enrichment.registration import parse_registration
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

    dns_task = analyze_dns(lookup.domain)
    backlinks_task = analyze_backlinks(lookup.domain, is_registered=is_registered)

    dns, backlinks = await asyncio.gather(dns_task, backlinks_task)

    registration = enrich_registration_age(registration)

    return DomainAnalysis(
        registration=registration,
        backlinks=backlinks,
        dns=dns,
    )
