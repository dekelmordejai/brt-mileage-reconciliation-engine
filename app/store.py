import hashlib
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else dumps(value).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,password TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('admin','analyst','reviewer','viewer')),active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),csrf TEXT NOT NULL,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,kind TEXT NOT NULL,name TEXT NOT NULL,sha TEXT NOT NULL,content BLOB NOT NULL,created TEXT NOT NULL,actor TEXT NOT NULL,UNIQUE(kind,sha));
CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,source_id TEXT NOT NULL REFERENCES sources(id),row_no INTEGER NOT NULL,data TEXT NOT NULL,raw TEXT NOT NULL,error TEXT,UNIQUE(source_id,row_no));
CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,created TEXT NOT NULL,actor TEXT NOT NULL,config TEXT NOT NULL,result TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY,created TEXT NOT NULL,actor TEXT NOT NULL,rv_id TEXT NOT NULL REFERENCES records(id),parent TEXT,payload TEXT NOT NULL,reason TEXT NOT NULL,evidence TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS decisions(id TEXT PRIMARY KEY,proposal_id TEXT UNIQUE NOT NULL REFERENCES proposals(id),actor TEXT NOT NULL,created TEXT NOT NULL,approved INTEGER NOT NULL,reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY AUTOINCREMENT,created TEXT NOT NULL,actor TEXT NOT NULL,event TEXT NOT NULL,payload TEXT NOT NULL,previous TEXT NOT NULL,hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS login_failures(ip TEXT PRIMARY KEY,count INTEGER NOT NULL,until REAL NOT NULL);
CREATE INDEX IF NOT EXISTS records_source ON records(source_id);
CREATE INDEX IF NOT EXISTS sources_kind ON sources(kind);
"""


class Store:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get("MOTOR_DB", "private_data/motor.sqlite3"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)
            for table in ("sources", "records", "runs", "proposals", "decisions", "audit"):
                for action in ("UPDATE", "DELETE"):
                    db.execute(
                        f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'Registro inmutable'); END"
                    )
            db.execute("PRAGMA user_version=1")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def audit(self, db, actor, event, payload):
        # SQLite serializa las escrituras: la cadena y la mutación comparten transacción.
        previous = db.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        previous = previous[0] if previous else "0" * 64
        stamp = now()
        payload = dumps(payload)
        h = digest([stamp, actor, event, payload, previous])
        db.execute(
            "INSERT INTO audit(created,actor,event,payload,previous,hash) VALUES(?,?,?,?,?,?)",
            (stamp, actor, event, payload, previous, h),
        )

    def records(self, db, kind):
        return [
            dict(id=r["id"], source_id=r["source_id"], row_no=r["row_no"], **json.loads(r["data"]))
            for r in db.execute(
                "SELECT r.* FROM records r JOIN sources s ON s.id=r.source_id WHERE s.kind=? AND r.error IS NULL ORDER BY s.created,r.row_no",
                (kind,),
            )
        ]

    def approved(self, db):
        rows = db.execute(
            "SELECT p.*,d.created AS approved_at FROM proposals p JOIN decisions d ON d.proposal_id=p.id WHERE d.approved=1 ORDER BY d.created,p.id"
        ).fetchall()
        result = {}
        for r in rows:
            result[r["rv_id"]] = dict(r) | {"payload": json.loads(r["payload"])}
        return result


def uid():
    return secrets.token_hex(12)
