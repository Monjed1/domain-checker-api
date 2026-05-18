from enum import Enum

from pydantic import BaseModel, Field, field_validator


class AvailabilityStatus(str, Enum):
    AVAILABLE = "available"
    REGISTERED = "registered"
    UNAVAILABLE = "unavailable"  # not registered but cannot be registered (reserved, etc.)
    UNKNOWN = "unknown"


class DomainCheckRequest(BaseModel):
    domains: list[str] = Field(..., min_length=1, description="Domain names to check")

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
    expiry_date: str | None = None
    message: str | None = None


class DomainCheckResponse(BaseModel):
    results: list[DomainResult]
    checked: int


class HealthResponse(BaseModel):
    status: str
    version: str = "1.0.0"
