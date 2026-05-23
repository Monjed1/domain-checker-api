from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.models import DropStatus, RegistrationInfo

# EPP / RDAP lifecycle statuses → drop phase
_DROP_STATUS_MAP: dict[str, DropStatus] = {
    "pending delete": DropStatus.PENDING_DELETE,
    "pendingdelete": DropStatus.PENDING_DELETE,
    "redemption period": DropStatus.REDEMPTION_PERIOD,
    "redemptionperiod": DropStatus.REDEMPTION_PERIOD,
    "pending restore": DropStatus.PENDING_RESTORE,
    "pendingrestore": DropStatus.PENDING_RESTORE,
    "add period": DropStatus.RECENTLY_REGISTERED,
    "addperiod": DropStatus.RECENTLY_REGISTERED,
}

_WHOIS_CREATION = re.compile(
    r"(?:creation date|created on|registered on|registration date)[:\s]+(.+)",
    re.IGNORECASE,
)
_WHOIS_EXPIRY = re.compile(
    r"(?:registry expiry|expir(?:y|ation) date|paid-till|expires on)[:\s]+(.+)",
    re.IGNORECASE,
)
_WHOIS_REGISTRAR = re.compile(r"registrar[:\s]+(.+)", re.IGNORECASE)
_WHOIS_STATUS = re.compile(r"domain status[:\s]+(.+)", re.IGNORECASE)


def parse_registration(
    *,
    is_registered: bool,
    rdap_payload: dict[str, Any] | None,
    whois_text: str | None,
    whois_record: Any | None,
) -> RegistrationInfo:
    if not is_registered:
        return RegistrationInfo(
            is_registered=False,
            drop_status=DropStatus.NOT_REGISTERED,
        )

    if rdap_payload:
        return _from_rdap(rdap_payload)

    if whois_record is not None or whois_text:
        return _from_whois(whois_record, whois_text or "")

    return RegistrationInfo(is_registered=True, drop_status=DropStatus.ACTIVE)


def _from_rdap(payload: dict[str, Any]) -> RegistrationInfo:
    creation = _rdap_event_date(payload, ("registration",))
    expiry = _rdap_event_date(payload, ("expiration", "registrar expiration"))
    registrar = _rdap_registrar(payload)
    statuses = _rdap_statuses(payload)
    drop_status = _drop_from_statuses(statuses)

    return RegistrationInfo(
        is_registered=True,
        creation_date=creation,
        expiration_date=expiry,
        registrar=registrar,
        domain_statuses=statuses,
        drop_status=drop_status,
    )


def _from_whois(record: Any | None, text: str) -> RegistrationInfo:
    creation = _field_date(record, "creation_date") or _regex_date(text, _WHOIS_CREATION)
    expiry = _field_date(record, "expiration_date") or _regex_date(text, _WHOIS_EXPIRY)
    registrar = _field_str(record, "registrar") or _regex_group(text, _WHOIS_REGISTRAR)
    statuses = _whois_statuses(record, text)
    drop_status = _drop_from_statuses(statuses)

    return RegistrationInfo(
        is_registered=True,
        creation_date=creation,
        expiration_date=expiry,
        registrar=registrar,
        domain_statuses=statuses,
        drop_status=drop_status,
    )


def _rdap_event_date(payload: dict[str, Any], actions: tuple[str, ...]) -> str | None:
    for event in payload.get("events", []):
        action = (event.get("eventAction") or "").lower()
        if action in actions:
            return _normalize_date(event.get("eventDate"))
    return None


def _rdap_registrar(payload: dict[str, Any]) -> str | None:
    for entity in payload.get("entities", []):
        roles = [r.lower() for r in entity.get("roles", [])]
        if "registrar" not in roles:
            continue
        vcard = entity.get("vcardArray")
        if isinstance(vcard, list) and len(vcard) > 1:
            for row in vcard[1]:
                if isinstance(row, list) and len(row) >= 4 and row[0] == "fn":
                    return str(row[3])
        if entity.get("handle"):
            return str(entity["handle"])
    return None


def _rdap_statuses(payload: dict[str, Any]) -> list[str]:
    statuses: list[str] = []
    for item in payload.get("status", []):
        if isinstance(item, str):
            statuses.append(item)
        elif isinstance(item, dict) and item.get("description"):
            statuses.append(str(item["description"]))
    return statuses


def _whois_statuses(record: Any | None, text: str) -> list[str]:
    raw = _field_value(record, "status")
    if raw is None:
        return [m.group(1).strip() for m in _WHOIS_STATUS.finditer(text)]
    if isinstance(raw, list):
        return [str(s) for s in raw]
    return [str(raw)]


def _drop_from_statuses(statuses: list[str]) -> DropStatus:
    combined = " ".join(statuses).lower()
    for key, drop in _DROP_STATUS_MAP.items():
        if key in combined:
            return drop
    if "client transfer prohibited" in combined or "ok" in combined or statuses:
        return DropStatus.ACTIVE
    return DropStatus.ACTIVE


def _normalize_date(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    if "T" in text:
        return text.split("T")[0]
    return text[:10] if len(text) >= 10 else text


def _field_value(record: Any | None, name: str) -> Any:
    if record is None:
        return None
    if isinstance(record, dict):
        return record.get(name)
    return getattr(record, name, None)


def _field_str(record: Any | None, name: str) -> str | None:
    value = _field_value(record, name)
    if value is None:
        return None
    if isinstance(value, list):
        value = value[0] if value else None
    return str(value).strip() if value else None


def _field_date(record: Any | None, name: str) -> str | None:
    value = _field_value(record, name)
    if value is None:
        return None
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    return _normalize_date(value)


def _regex_date(text: str, pattern: re.Pattern[str]) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    return _normalize_date(match.group(1).strip())


def _regex_group(text: str, pattern: re.Pattern[str]) -> str | None:
    match = pattern.search(text)
    return match.group(1).strip() if match else None
