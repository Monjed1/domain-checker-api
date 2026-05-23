from __future__ import annotations

import asyncio

from app.enrichment.pipeline import build_domain_analysis
from app.lookup import LookupResult, domain_lookup
from app.models import DomainAnalysis, DomainResult


class DomainChecker:
    async def check_many(self, domains: list[str], *, enrich: bool = True) -> list[DomainResult]:
        lookups = await domain_lookup.lookup_many(domains)
        if not enrich:
            return [_to_result(lookup, None) for lookup in lookups]

        enriched = await asyncio.gather(*[_enrich_one(lookup) for lookup in lookups])
        return list(enriched)


async def _enrich_one(lookup: LookupResult) -> DomainResult:
    analysis = await build_domain_analysis(lookup)
    return _to_result(lookup, analysis)


def _to_result(lookup: LookupResult, analysis: DomainAnalysis | None) -> DomainResult:
    creation = None
    expiry = lookup.expiry_date
    registrar = lookup.registrar

    age_days = None
    age_years = None
    age_human = None
    was_registered_before = False

    if analysis:
        reg = analysis.registration
        creation = reg.creation_date
        expiry = reg.expiration_date or expiry
        registrar = reg.registrar or registrar
        age_days = reg.domain_age_days
        age_years = reg.domain_age_years
        age_human = reg.domain_age_human
        was_registered_before = reg.was_registered_before

    return DomainResult(
        domain=lookup.domain,
        status=lookup.status,
        available=lookup.available,
        method=lookup.method,
        registrar=registrar,
        creation_date=creation,
        expiry_date=expiry,
        was_registered_before=was_registered_before,
        domain_age_days=age_days,
        domain_age_years=age_years,
        domain_age_human=age_human,
        message=lookup.message,
        analysis=analysis,
    )


checker = DomainChecker()
