"""CSV ingestion with original-byte fingerprints and immutable raw row snapshots."""

import csv
import hashlib
import io
from datetime import datetime, timezone
from pathlib import Path

from .models import IngestedFile, SourceFile, SourceRecord, ValidationError

COMMON_COLUMNS = frozenset(
    {
        "service_date",
        "vehicle_id",
        "route",
        "start_time",
        "end_time",
        "start_day_offset",
        "end_day_offset",
        "km",
        "jornada",
    }
)


def read_csv(path: str | Path, kind: str) -> IngestedFile:
    """Read only; logical row position (header is row 1) is not a physical trip ID."""
    if kind not in {"pasos", "rv"}:
        raise ValidationError("source kind must be 'pasos' or 'rv'")
    source_path = Path(path)
    content = source_path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    try:
        reader = csv.reader(io.StringIO(content.decode("utf-8-sig")), strict=True)
        columns = tuple(next(reader, ()))
        if not columns or len(columns) != len(set(columns)):
            raise ValidationError("CSV requires nonempty, unique column names")
        if any(not column.strip() for column in columns):
            raise ValidationError("CSV column names cannot be blank")
        required = COMMON_COLUMNS | ({"status"} if kind == "rv" else set())
        missing = sorted(required - set(columns))
        if missing:
            raise ValidationError(f"missing columns: {', '.join(missing)}")
        rows = []
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(columns):
                raise ValidationError(f"row {row_number}: expected {len(columns)} fields")
            rows.append(
                SourceRecord(
                    id=f"{kind}:{digest}:{row_number}",
                    file_hash=digest,
                    row_number=row_number,
                    raw=tuple(zip(columns, row, strict=True)),
                )
            )
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValidationError(f"invalid UTF-8 CSV: {exc}") from exc
    manifest = SourceFile(
        name=source_path.name,
        path=str(source_path.resolve()),
        kind=kind,
        sha256=digest,
        columns=columns,
        imported_at=datetime.now(timezone.utc),
    )
    return IngestedFile(manifest, tuple(rows))
