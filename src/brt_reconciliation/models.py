"""Small immutable administrative models, separate from future physical identities."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum


class ValidationError(ValueError):
    """Input cannot be interpreted under the explicit synthetic contract."""


@dataclass(frozen=True)
class SourceFile:
    name: str
    path: str
    kind: str
    sha256: str
    columns: tuple[str, ...]
    imported_at: datetime


@dataclass(frozen=True)
class SourceRecord:
    id: str
    file_hash: str
    row_number: int
    raw: tuple[tuple[str, str], ...]

    def values(self) -> dict[str, str]:
        """Return a mutable copy, never expose mutable stored values."""
        return dict(self.raw)


@dataclass(frozen=True)
class IngestedFile:
    manifest: SourceFile
    records: tuple[SourceRecord, ...]


@dataclass(frozen=True)
class Trip:
    source: SourceRecord
    service_date: date
    vehicle_id: str
    route: str
    start: datetime
    end: datetime
    km: Decimal
    jornada: str | None
    status: str | None


class MatchState(StrEnum):
    CANDIDATE = "CANDIDATE"
    UNEQUIVOCAL = "UNEQUIVOCAL"
    AMBIGUOUS = "AMBIGUOUS"
    DISCARDED = "DISCARDED"
    APPROVED = "APPROVED"


@dataclass(frozen=True)
class Match:
    pasos_id: str
    rv_id: str
    state: MatchState
    reasons: tuple[str, ...]
