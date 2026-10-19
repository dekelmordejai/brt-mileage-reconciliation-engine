"""Copia consistente de SQLite, incluso con WAL activo; contiene datos privados."""

import argparse
import sqlite3
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("source")
parser.add_argument("destination")
args = parser.parse_args()
if Path(args.destination).exists():
    raise SystemExit("El destino ya existe; se evita sobrescribir un respaldo")
with sqlite3.connect(args.source) as source, sqlite3.connect(args.destination) as destination:
    source.backup(destination)
    assert destination.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
print("Respaldo privado verificado. Manténgalo fuera de GitHub.")
