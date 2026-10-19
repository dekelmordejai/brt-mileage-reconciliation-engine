"""Normalize derived values without overwriting source rows or inventing dates."""

import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from .models import SourceRecord, Trip, ValidationError


def optional_identifier(raw: str) -> str | None:
    value = raw.strip()
    return None if value in {"", "-"} else value


def nonnegative_decimal(raw: str) -> Decimal:
    try:
        value = Decimal(raw.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValidationError(f"invalid decimal: {raw!r}") from exc
    if not value.is_finite() or value < 0:
        raise ValidationError("distance must be finite and nonnegative")
    return value


def normalize_km2(raw: str) -> Decimal | None:
    """0 is uncaptured in KM2 only; positive documentary amount is not approval."""
    if raw.strip() in {"", "-"}:
        return None
    value = nonnegative_decimal(raw)
    return value if value > 0 else None


def local_instant(service_date: date, clock: str, day_offset: str) -> datetime:
    if not re.fullmatch(r"\d{2}:\d{2}(?::\d{2})?", clock.strip()):
        raise ValidationError(f"invalid clock: {clock!r}")
    if not re.fullmatch(r"\d+", day_offset.strip()):
        raise ValidationError("day offset must be an explicit nonnegative integer")
    try:
        actual_date = service_date + timedelta(days=int(day_offset.strip()))
        return datetime.combine(actual_date, time.fromisoformat(clock.strip()))
    except (ValueError, OverflowError) as exc:
        raise ValidationError(f"invalid clock or calendar offset: {clock!r}") from exc


def normalize_checkpoints(
    service_date: date, checkpoints: tuple[tuple[str, str], ...]
) -> tuple[datetime, ...]:
    """Offsets explicit; reject bad chronology rather than roll over silently."""
    result = tuple(local_instant(service_date, clock, offset) for clock, offset in checkpoints)
    if any(later <= earlier for earlier, later in zip(result, result[1:], strict=False)):
        raise ValidationError("checkpoints must be strictly increasing")
    return result


def normalize_trip(record: SourceRecord) -> Trip:
    values = record.values()
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", values["service_date"].strip()):
            raise ValidationError("service_date requires ISO YYYY-MM-DD")
        service_date = date.fromisoformat(values["service_date"].strip())
        vehicle = optional_identifier(values["vehicle_id"])
        route = optional_identifier(values["route"])
        if vehicle is None or route is None:
            raise ValidationError("vehicle_id and route are required")
        start = local_instant(service_date, values["start_time"], values["start_day_offset"])
        end = local_instant(service_date, values["end_time"], values["end_day_offset"])
        if end <= start:
            raise ValidationError("end must be after start; specify midnight offsets explicitly")
        return Trip(
            source=record,
            service_date=service_date,
            vehicle_id=vehicle,
            route=route,
            start=start,
            end=end,
            km=nonnegative_decimal(values["km"]),
            jornada=optional_identifier(values["jornada"]),
            status=optional_identifier(values.get("status", "")),
        )
    except (KeyError, ValueError) as exc:
        raise ValidationError(f"{record.id}: {exc}") from exc
