from fastapi import Depends, FastAPI, Header, HTTPException, Query, status

from app.checker import checker
from app.config import settings
from app.models import DomainCheckRequest, DomainCheckResponse, DomainResult, HealthResponse

app = FastAPI(
    title="Domain Availability API",
    description=(
        "Check domain availability plus protocol-based analysis: "
        "RDAP/WHOIS registration, live DNS, and limited homepage probe. "
        "No paid SEO APIs."
    ),
    version="2.1.0",
)


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Send header: X-API-Key",
        )


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/supported-tlds")
async def supported_tlds() -> dict[str, list[str]]:
    from app.registries import TLD_REGISTRIES

    return {
        "registry_whois": sorted(TLD_REGISTRIES.keys()),
        "note": "Many other TLDs (.com, .net, .org, etc.) work via IANA RDAP bootstrap.",
    }


@app.get("/analysis-capabilities")
async def analysis_capabilities() -> dict:
    return {
        "registration": {
            "source": "RDAP / WHOIS (registry protocols)",
            "fields": [
                "is_registered",
                "creation_date",
                "expiration_date",
                "registrar",
                "domain_statuses",
                "drop_status",
                "was_registered_before",
                "domain_age_days",
                "domain_age_years",
                "domain_age_human",
                "age_source",
            ],
        },
        "dns": {
            "source": "Live DNS (dnspython)",
            "fields": [
                "a_records",
                "mx_hosts",
                "ns_hosts",
                "likely_parked",
                "had_live_hosting",
            ],
            "limit": "No paid DNS-history database — current DNS only.",
        },
        "backlinks": {
            "source": "Homepage HTTP probe only",
            "limit": "Real inbound backlink index requires Ahrefs/Moz/etc. Not included.",
        },
    }


@app.post("/check", response_model=DomainCheckResponse, dependencies=[Depends(verify_api_key)])
async def check_domains(body: DomainCheckRequest) -> DomainCheckResponse:
    if len(body.domains) > settings.max_domains_per_request:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {settings.max_domains_per_request} domains per request",
        )

    results = await checker.check_many(body.domains, enrich=body.enrich)
    return DomainCheckResponse(results=results, checked=len(results))


@app.get("/check/{domain}", response_model=DomainResult, dependencies=[Depends(verify_api_key)])
async def check_single_domain(
    domain: str,
    enrich: bool = Query(True, description="Include full domain analysis"),
) -> DomainResult:
    results = await checker.check_many([domain], enrich=enrich)
    return results[0]


@app.get("/check", response_model=DomainCheckResponse, dependencies=[Depends(verify_api_key)])
async def check_domains_query(
    domains: str = Query(..., description="Comma-separated domain names"),
    enrich: bool = Query(True, description="Include full domain analysis"),
) -> DomainCheckResponse:
    domain_list = [d.strip() for d in domains.split(",") if d.strip()]
    if not domain_list:
        raise HTTPException(status_code=400, detail="Provide at least one domain")

    if len(domain_list) > settings.max_domains_per_request:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {settings.max_domains_per_request} domains per request",
        )

    results = await checker.check_many(domain_list, enrich=enrich)
    return DomainCheckResponse(results=results, checked=len(results))
