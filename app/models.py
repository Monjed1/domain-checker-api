from enum import Enum

from pydantic import BaseModel, Field, field_validator


class AvailabilityStatus(str, Enum):
    AVAILABLE = "available"
    REGISTERED = "registered"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class DropStatus(str, Enum):
    NOT_REGISTERED = "not_registered"
    ACTIVE = "active"
    PENDING_DELETE = "pending_delete"
    REDEMPTION_PERIOD = "redemption_period"
    PENDING_RESTORE = "pending_restore"
    RECENTLY_REGISTERED = "recently_registered"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RegistrationInfo(BaseModel):
    is_registered: bool
    creation_date: str | None = None
    expiration_date: str | None = None
    registrar: str | None = None
    domain_statuses: list[str] = Field(default_factory=list)
    drop_status: DropStatus = DropStatus.UNKNOWN
    was_registered_before: bool = False
    domain_age_days: int | None = None
    domain_age_years: float | None = None
    domain_age_human: str | None = None
    age_source: str | None = None
    first_seen_date: str | None = None
    age_note: str | None = None


class WaybackInfo(BaseModel):
    was_archived: bool = False
    snapshot_count: int = 0
    first_seen: str | None = None
    last_seen: str | None = None
    likely_real_business: bool = False
    risk_flags: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.NONE
    sample_urls: list[str] = Field(default_factory=list)
    lookup_status: str = "unknown"  # ok | not_found | partial | rate_limited | error
    rate_limited: bool = False
    source: str = "internet_archive_cdx"
    note: str | None = None


class BacklinkInfo(BaseModel):
    supported: bool = False
    method: str | None = None
    referring_domains_count: int | None = None
    referring_domains_sample: list[str] = Field(default_factory=list)
    anchor_text_samples: list[str] = Field(default_factory=list)
    note: str | None = None


class DnsHistoryInfo(BaseModel):
    resolves: bool = False
    a_records: list[str] = Field(default_factory=list)
    aaaa_records: list[str] = Field(default_factory=list)
    mx_hosts: list[str] = Field(default_factory=list)
    ns_hosts: list[str] = Field(default_factory=list)
    txt_samples: list[str] = Field(default_factory=list)
    cnames: list[str] = Field(default_factory=list)
    likely_parked: bool = False
    had_live_hosting: bool = False
    had_email_setup: bool = False
    inferred_historical_hosting: bool = False
    likely_spam_or_parked_history: bool = False
    note: str | None = None
    lookup_errors: list[str] = Field(default_factory=list)


class DomainAnalysis(BaseModel):
    registration: RegistrationInfo
    wayback: WaybackInfo
    backlinks: BacklinkInfo
    dns: DnsHistoryInfo


class DomainCheckRequest(BaseModel):
    domains: list[str] = Field(..., min_length=1, description="Domain names to check")
    enrich: bool = Field(
        True,
        description="Include registration, Wayback, DNS, and backlink probe analysis",
    )

    @field_validator("domains")
    @classmethod
    def strip_domains(cls, values: list[str]) -> list[str]:
        cleaned = [v.strip().lower() for v in values if v and v.strip()]
        if not cleaned:
            raise ValueError("At least one valid domain is required")
        return cleaned


class DomainResult(BaseModel):
    domain: str
    status: AvailabilityStatus
    available: bool
    method: str
    registrar: str | None = None
    creation_date: str | None = None
    expiry_date: str | None = None
    was_registered_before: bool = False
    domain_age_days: int | None = None
    domain_age_years: float | None = None
    domain_age_human: str | None = None
    message: str | None = None
    analysis: DomainAnalysis | None = None


class DomainCheckResponse(BaseModel):
    results: list[DomainResult]
    checked: int


class HealthResponse(BaseModel):
    status: str
    version: str = "2.0.0"
