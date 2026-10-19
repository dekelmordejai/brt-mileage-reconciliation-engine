"""Executable synthetic diagnostic report; never produce payable mileage."""

import argparse
import json
import sys
from dataclasses import asdict

from . import CONCEPTUAL_VERSION, __version__
from .ingestion import read_csv
from .matching import associate
from .models import MatchState, ValidationError
from .normalization import nonnegative_decimal, normalize_trip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pasos")
    parser.add_argument("rv")
    parser.add_argument("--time-tolerance-seconds", required=True, type=int)
    parser.add_argument("--km-tolerance", required=True)
    args = parser.parse_args(argv)
    try:
        km_tolerance = nonnegative_decimal(args.km_tolerance)
        p_file, r_file = read_csv(args.pasos, "pasos"), read_csv(args.rv, "rv")
        pasos = tuple(normalize_trip(record) for record in p_file.records)
        rv = tuple(normalize_trip(record) for record in r_file.records)
        matches = associate(
            pasos,
            rv,
            time_tolerance_seconds=args.time_tolerance_seconds,
            km_tolerance=km_tolerance,
        )
        compatible = [match for match in matches if match.state != MatchState.DISCARDED]
        used_p = {match.pasos_id for match in compatible}
        used_r = {match.rv_id for match in compatible}
        report = {
            "schema_version": 1,
            "software_version": __version__,
            "conceptual_version": CONCEPTUAL_VERSION,
            "notice": "Candidate associations only; no physical validation or payment approval",
            "sources": [asdict(p_file.manifest), asdict(r_file.manifest)],
            "matching_config": {
                "time_tolerance_seconds": args.time_tolerance_seconds,
                "km_tolerance": str(km_tolerance),
                "policy": "bidirectional-degree-one",
            },
            "matches": [asdict(match) for match in matches],
            "unmatched_pasos": [trip.source.id for trip in pasos if trip.source.id not in used_p],
            "unmatched_rv": [trip.source.id for trip in rv if trip.source.id not in used_r],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0
    except (OSError, ValidationError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
