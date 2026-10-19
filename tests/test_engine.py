"""Synthetic regressions for approved baseline behavior, not production accuracy."""

import hashlib
import json
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from brt_reconciliation.ingestion import read_csv
from brt_reconciliation.matching import associate
from brt_reconciliation.models import MatchState, ValidationError
from brt_reconciliation.normalization import (
    local_instant,
    nonnegative_decimal,
    normalize_checkpoints,
    normalize_km2,
    normalize_trip,
    optional_identifier,
)

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "synthetic"


def trips(kind):
    imported = read_csv(FIXTURES / f"{kind}.csv", kind)
    return tuple(normalize_trip(record) for record in imported.records)


def matching(pasos, rv):
    return associate(pasos, rv, time_tolerance_seconds=60, km_tolerance=Decimal("0.01"))


def test_ingestion_preserves_bytes_raw_rows_and_reimport_identity():
    path = FIXTURES / "pasos.csv"
    original = path.read_bytes()
    first, second = read_csv(path, "pasos"), read_csv(path, "pasos")
    assert first.manifest.sha256 == hashlib.sha256(original).hexdigest()
    assert first.manifest.imported_at.tzinfo is not None
    assert first.records == second.records
    assert first.records[1].values()["jornada"] == "-"
    assert path.read_bytes() == original
    copy = first.records[0].values()
    copy["km"] = "999"
    assert first.records[0].values()["km"] == "10.25"
    with pytest.raises(FrozenInstanceError):
        first.records[0].id = "changed"


@pytest.mark.parametrize(
    "text",
    [
        "vehicle_id,km\nSYN-001,1\n",
        "service_date,service_date\n2026-09-28,2026-09-28\n",
        "\n",
    ],
)
def test_invalid_schema_is_rejected(tmp_path, text):
    path = tmp_path / "synthetic.csv"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValidationError):
        read_csv(path, "pasos")


def test_malformed_row_rejected_without_partial_result(tmp_path):
    path = tmp_path / "synthetic.csv"
    header = (FIXTURES / "pasos.csv").read_text().splitlines()[0]
    path.write_text(header + "\nSYN-001,extra\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="row 2"):
        read_csv(path, "pasos")


def test_empty_but_valid_source_has_manifest_and_no_records(tmp_path):
    path = tmp_path / "synthetic.csv"
    header = (FIXTURES / "pasos.csv").read_text().splitlines()[0]
    path.write_text(header + "\n", encoding="utf-8")
    assert read_csv(path, "pasos").records == ()


def test_source_kind_distinguishes_administrative_identity():
    a = read_csv(FIXTURES / "rv.csv", "pasos")
    b = read_csv(FIXTURES / "rv.csv", "rv")
    assert a.manifest.sha256 == b.manifest.sha256
    assert a.records[0].id != b.records[0].id


def test_unknown_source_kind_rejected():
    with pytest.raises(ValidationError):
        read_csv(FIXTURES / "rv.csv", "support")


@pytest.mark.parametrize("raw", ["0", "0.00", "-", "", " 0 "])
def test_km2_uncaptured(raw):
    assert normalize_km2(raw) is None


def test_positive_km2_and_trip_zero_have_different_semantics():
    assert normalize_km2("12.34") == Decimal("12.34")
    assert nonnegative_decimal("0") == Decimal("0")


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-1", "abc", "-"])
def test_invalid_distance(raw):
    with pytest.raises(ValidationError):
        nonnegative_decimal(raw)


def test_decimal_precision_retained_and_identifier_zeroes_preserved():
    assert nonnegative_decimal("0.1") + nonnegative_decimal("0.2") == Decimal("0.3")
    assert nonnegative_decimal("1.2345") == Decimal("1.2345")
    assert optional_identifier(" 001 ") == "001"
    assert trips("pasos")[1].jornada is None
    assert trips("pasos")[1].source.values()["jornada"] == "-"


def test_midnight_requires_explicit_calendar_offset():
    trip = trips("pasos")[0]
    assert trip.end - trip.start == timedelta(minutes=30)
    assert trip.service_date == date(2026, 9, 28)
    assert trip.end.date() == date(2026, 9, 29)
    raw = trip.source.values()
    raw["end_day_offset"] = "0"
    with pytest.raises(ValidationError, match="midnight"):
        normalize_trip(replace(trip.source, raw=tuple(raw.items())))


@pytest.mark.parametrize(
    "clock,offset", [("25:00", "0"), ("8:00", "0"), ("08:00", ""), ("08:00", "-1")]
)
def test_invalid_time_or_missing_offset(clock, offset):
    with pytest.raises(ValidationError):
        local_instant(date(2026, 9, 28), clock, offset)


def test_checkpoint_order_and_explicit_midnight():
    result = normalize_checkpoints(date(2026, 9, 28), (("23:58", "0"), ("00:02", "1")))
    assert result[1] > result[0]
    with pytest.raises(ValidationError, match="strictly increasing"):
        normalize_checkpoints(date(2026, 9, 28), (("08:05", "0"), ("08:00", "0")))


def test_unique_midnight_association_never_means_approval():
    result = matching(trips("pasos")[:1], trips("rv")[:1])
    assert len(result) == 1
    assert result[0].state == MatchState.UNEQUIVOCAL
    assert "not physical or economic approval" in result[0].reasons[0]


def test_two_rv_rows_compete_for_one_pasos_without_reuse():
    result = matching(trips("pasos")[1:2], trips("rv")[1:3])
    assert len(result) == 2
    assert all(match.state == MatchState.AMBIGUOUS for match in result)


def test_two_pasos_rows_compete_for_one_rv_without_forced_choice():
    p = trips("pasos")[0]
    duplicate = replace(p, source=replace(p.source, id=p.source.id + ":synthetic-other"))
    result = matching((p, duplicate), trips("rv")[:1])
    assert all(match.state == MatchState.AMBIGUOUS for match in result)


def test_equal_mileage_at_different_times_is_not_identity():
    p = trips("pasos")[0]
    shifted = replace(
        p,
        source=replace(p.source, id=p.source.id + ":later"),
        start=p.start + timedelta(hours=3),
        end=p.end + timedelta(hours=3),
    )
    result = matching((p, shifted), trips("rv")[:1])
    assert [match.state for match in result].count(MatchState.UNEQUIVOCAL) == 1
    assert [match.state for match in result].count(MatchState.DISCARDED) == 1


def test_confirmed_jornada_conflict_is_discarded_and_missing_is_not_inferred():
    r = trips("rv")[0]
    result = matching(trips("pasos")[:1], (replace(r, jornada="SYN-OTHER-DUTY"),))
    assert result[0].state == MatchState.DISCARDED
    assert result[0].reasons == ("declared Jornada conflict",)
    missing = replace(r, jornada=None)
    assert matching(trips("pasos")[:1], (missing,))[0].state == MatchState.UNEQUIVOCAL
    assert missing.jornada is None


def test_cancelled_positive_km_is_preserved_without_physical_conclusion():
    r = trips("rv")[3]
    assert r.status == "Cancelada" and r.km == Decimal("5.00")
    assert matching(trips("pasos")[2:], (r,))[0].state == MatchState.UNEQUIVOCAL
    assert r.status == "Cancelada"


def test_no_realizado_zero_is_schedule_record_not_generated_physical_mileage():
    r = trips("rv")[4]
    assert r.status == "No Realizado" and r.km == 0
    assert matching(trips("pasos"), (r,)) == ()


def test_uniqueness_is_invariant_to_input_order():
    p, r = trips("pasos"), trips("rv")
    assert matching(p, r) == matching(tuple(reversed(p)), tuple(reversed(r)))
    unique = [m for m in matching(p, r) if m.state == MatchState.UNEQUIVOCAL]
    assert len({m.pasos_id for m in unique}) == len(unique)
    assert len({m.rv_id for m in unique}) == len(unique)


@pytest.mark.parametrize(
    "seconds,km",
    [(-1, Decimal("0")), (True, Decimal("0")), (1, Decimal("NaN")), (1, Decimal("-1")), (1, 0.1)],
)
def test_invalid_matching_tolerances(seconds, km):
    with pytest.raises(ValidationError):
        associate((), (), time_tolerance_seconds=seconds, km_tolerance=km)


def test_repeated_source_row_rejected():
    p = trips("pasos")[0]
    with pytest.raises(ValidationError, match="cannot be repeated"):
        matching((p, p), trips("rv")[:1])


def test_cli_runs_from_outside_checkout_and_reports_uncertainty(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "brt_reconciliation",
            str(FIXTURES / "pasos.csv"),
            str(FIXTURES / "rv.csv"),
            "--time-tolerance-seconds",
            "60",
            "--km-tolerance",
            "0.01",
        ],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=True,
    )
    report = json.loads(completed.stdout)
    assert report["software_version"] == "0.1.0"
    assert report["conceptual_version"] == "2.8"
    assert len(report["matches"]) == 4
    assert len(report["unmatched_rv"]) == 1
    assert {m["state"] for m in report["matches"]} == {"UNEQUIVOCAL", "AMBIGUOUS"}
    assert "payable_km" not in report


def test_cli_bad_input_has_error_exit_and_no_partial_output(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "brt_reconciliation",
            str(tmp_path / "missing.csv"),
            str(FIXTURES / "rv.csv"),
            "--time-tolerance-seconds",
            "60",
            "--km-tolerance",
            "0",
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2
    assert "Input error" in result.stderr
    assert result.stdout == ""
