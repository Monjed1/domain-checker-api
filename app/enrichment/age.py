from __future__ import annotations

from datetime import date, datetime

from app.models import RegistrationInfo, WaybackInfo


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None

    candidates = (
        text[:10],
        text[:19].replace("Z", ""),
    )
    formats = ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d-%b-%Y", "%Y/%m/%d")
    for candidate in candidates:
        for fmt in formats:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def compute_age_days(start: date, end: date | None = None) -> int:
    end = end or date.today()
    return max(0, (end - start).days)


def format_age_human(days: int) -> str:
    if days < 1:
        return "less than 1 day"

    years, remainder = divmod(days, 365)
    months, day_rem = divmod(remainder, 30)

    parts: list[str] = []
    if years:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if months:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    if not years and not months:
        parts.append(f"{day_rem} day{'s' if day_rem != 1 else ''}")
    return ", ".join(parts)


def age_years_from_days(days: int) -> float:
    return round(days / 365.25, 1)


def enrich_registration_age(
    registration: RegistrationInfo,
    wayback: WaybackInfo | None,
) -> RegistrationInfo:
    """Set domain age from registry creation date, or approximate from Wayback if dropped."""
    if registration.is_registered and registration.creation_date:
        start = parse_date(registration.creation_date)
        if start:
            days = compute_age_days(start)
            return registration.model_copy(
                update={
                    "was_registered_before": True,
                    "domain_age_days": days,
                    "domain_age_years": age_years_from_days(days),
                    "domain_age_human": format_age_human(days),
                    "age_source": "registry_creation_date",
                }
            )

    if (
        not registration.is_registered
        and wayback
        and wayback.was_archived
        and wayback.first_seen
    ):
        start = parse_date(wayback.first_seen)
        end = parse_date(wayback.last_seen) if wayback.last_seen else date.today()
        if start:
            days = compute_age_days(start, end)
            note = (
                "Approximate age from Wayback first archive date "
                "(not exact registration date)."
            )
            return registration.model_copy(
                update={
                    "was_registered_before": True,
                    "domain_age_days": days,
                    "domain_age_years": age_years_from_days(days),
                    "domain_age_human": format_age_human(days),
                    "age_source": "wayback_approximate",
                    "first_seen_date": wayback.first_seen,
                    "age_note": note,
                }
            )

    if registration.is_registered:
        return registration.model_copy(update={"was_registered_before": True})

    return registration
