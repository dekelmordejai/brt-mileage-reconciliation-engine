"""Conservative candidate graph. No physical validation or economic approval."""

from collections import Counter
from datetime import timedelta
from decimal import Decimal

from .models import Match, MatchState, Trip, ValidationError


def associate(
    pasos: tuple[Trip, ...],
    rv: tuple[Trip, ...],
    *,
    time_tolerance_seconds: int,
    km_tolerance: Decimal,
) -> tuple[Match, ...]:
    if type(time_tolerance_seconds) is not int or time_tolerance_seconds < 0:
        raise ValidationError("time tolerance must be a nonnegative integer")
    if not isinstance(km_tolerance, Decimal) or not km_tolerance.is_finite() or km_tolerance < 0:
        raise ValidationError("km tolerance must be a finite nonnegative Decimal")
    ids = [trip.source.id for trip in (*pasos, *rv)]
    if len(ids) != len(set(ids)):
        raise ValidationError("input rows cannot be repeated; source IDs must be unique")
    try:
        tolerance = timedelta(seconds=time_tolerance_seconds)
    except OverflowError as exc:
        raise ValidationError("time tolerance exceeds supported range") from exc
    candidates: list[tuple[str, str]] = []
    discarded: list[Match] = []
    for p in pasos:
        for r in rv:
            if p.vehicle_id != r.vehicle_id or p.service_date != r.service_date:
                continue
            reasons = []
            if p.route != r.route:
                reasons.append("route mismatch")
            if p.jornada is not None and r.jornada is not None and p.jornada != r.jornada:
                reasons.append("declared Jornada conflict")
            if abs(p.start - r.start) > tolerance or abs(p.end - r.end) > tolerance:
                reasons.append("time outside configured tolerance")
            if abs(p.km - r.km) > km_tolerance:
                reasons.append("distance outside configured tolerance")
            if reasons:
                discarded.append(
                    Match(p.source.id, r.source.id, MatchState.DISCARDED, tuple(reasons))
                )
            else:
                candidates.append((p.source.id, r.source.id))
    p_counts = Counter(p for p, _ in candidates)
    r_counts = Counter(r for _, r in candidates)
    result = list(discarded)
    for p, r in candidates:
        unique = p_counts[p] == 1 and r_counts[r] == 1
        result.append(
            Match(
                p,
                r,
                MatchState.UNEQUIVOCAL if unique else MatchState.AMBIGUOUS,
                (
                    "unique under configured criteria; not physical or economic approval"
                    if unique
                    else "competing compatible source rows; review required",
                ),
            )
        )
    return tuple(sorted(result, key=lambda match: (match.pasos_id, match.rv_id)))
