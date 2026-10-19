import csv
import io
import json
import os
import secrets
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .engine import amount, interval, reconcile
from .importers import KINDS, clock, normalize, read_table
from .security import password_hash, verify
from .store import Store, digest, dumps, now, uid


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(StrictModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=1024)


class UserInput(StrictModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=1024)
    role: Literal["admin", "analyst", "reviewer", "viewer"]


class RunInput(StrictModel):
    line: str = Field(default="L1", pattern=r"^L[1-9][0-9]?$")
    year: int = Field(default=2026, ge=2020, le=2100)
    week: int = Field(default=40, ge=1, le=53)
    sources: list[str] = Field(min_length=1, max_length=100)


class Segment(StrictModel):
    start_km: str
    end_km: str
    evidence_ids: list[str] = Field(min_length=1, max_length=50)
    origin: str = Field(min_length=1, max_length=200)
    destination: str = Field(min_length=1, max_length=200)
    departure: str = ""
    arrival: str = ""


class Proposal(StrictModel):
    rv_id: str
    parent: str | None = None
    segments: list[Segment] = Field(max_length=100)
    cleared_events: list[str] = Field(default_factory=list, max_length=100)
    economic_company: str = Field(default="", max_length=100)
    resolution: Literal["validate", "reject"] = "validate"
    reason: str = Field(min_length=12, max_length=4000)
    evidence: str = Field(min_length=8, max_length=4000)


class Decision(StrictModel):
    approved: bool
    reason: str = Field(min_length=12, max_length=4000)


def import_source(store, db, kind, filename, data, actor, sheet=None):
    if kind not in KINDS:
        raise ValueError("Tipo de fuente no admitido")
    sha = digest(data)
    old = db.execute("SELECT id FROM sources WHERE kind=? AND sha=?", (kind, sha)).fetchone()
    if old:
        return {"id": old["id"], "duplicate": True}
    rows = read_table(data, filename, sheet)
    if not rows:
        raise ValueError("Archivo vacío")
    if len(rows) > 300000:
        raise ValueError("Máximo 300000 filas por archivo")
    sid = uid()
    errors = []
    db.execute(
        "INSERT INTO sources VALUES(?,?,?,?,?,?,?)",
        (sid, kind, Path(filename).name, sha, data, now(), actor),
    )
    for i, raw in enumerate(rows, 2):
        error = None
        normalized = {}
        try:
            normalized = normalize(kind, raw)
        except (ValueError, TypeError, KeyError) as exc:
            error = str(exc)
            if len(errors) < 30:
                errors.append({"row": i, "error": error})
        db.execute(
            "INSERT INTO records VALUES(?,?,?,?,?,?)",
            (digest([sid, i]), sid, i, dumps(normalized), dumps(raw), error),
        )
    store.audit(
        db, actor, "SOURCE_IMPORTED", {"id": sid, "kind": kind, "sha256": sha, "rows": len(rows)}
    )
    invalid = db.execute(
        "SELECT COUNT(*) FROM records WHERE source_id=? AND error IS NOT NULL", (sid,)
    ).fetchone()[0]
    return {
        "id": sid,
        "sha256": sha,
        "rows": len(rows),
        "invalid": invalid,
        "errors": errors,
        "duplicate": False,
    }


def create_app(path=None):
    app = FastAPI(title="BRT Mileage Reconciliation — Portfolio Demo", version="1.0.0")
    store = Store(path)
    app.state.store = store
    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.middleware("http")
    async def headers(request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        allowed = os.environ.get("MOTOR_HOSTS", "127.0.0.1,localhost,testserver").split(",")
        if host not in allowed:
            return Response("Host no permitido", status_code=400)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        return response

    def actor(request: Request):
        token = request.cookies.get("motor_session", "")
        with store.connect() as db:
            user = db.execute(
                "SELECT u.id,u.role,s.csrf FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>? AND u.active=1",
                (digest(token), time.time()),
            ).fetchone()
        if not user:
            raise HTTPException(401, "Inicia sesión")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not secrets.compare_digest(
            request.headers.get("X-CSRF-Token", ""), user["csrf"]
        ):
            raise HTTPException(403, "Protección CSRF: actualiza la sesión")
        return dict(user)

    def roles(*allowed):
        def check(user=Depends(actor)):
            if user["role"] not in allowed:
                raise HTTPException(403, "Rol sin autorización para esta acción")
            return user

        return check

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    @app.get("/healthz")
    def health():
        return {"status": "ok", "liquidation": "disabled"}

    @app.post("/api/login")
    def login(body: Login, request: Request, response: Response):
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Origen no permitido")
        ip = request.client.host if request.client else "local"
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            failure = db.execute("SELECT * FROM login_failures WHERE ip=?", (ip,)).fetchone()
            if failure and failure["count"] >= 10 and failure["until"] > time.time():
                raise HTTPException(429, "Espera 15 minutos antes de reintentar")
            u = db.execute(
                "SELECT * FROM users WHERE id=? AND active=1", (body.username,)
            ).fetchone()
            valid = (
                verify(body.password, u["password"])
                if u
                else verify(body.password, password_hash("dummy-password-irrelevant"))
            )
            if not u or not valid:
                count = (failure["count"] if failure and failure["until"] > time.time() else 0) + 1
                db.execute(
                    "INSERT OR REPLACE INTO login_failures VALUES(?,?,?)",
                    (ip, count, time.time() + 900),
                )
                store.audit(db, "anonymous", "LOGIN_FAILED", {"ip_hash": digest(ip)})
                db.commit()
                raise HTTPException(401, "Credenciales inválidas")
            db.execute("DELETE FROM login_failures WHERE ip=?", (ip,))
            token = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(32)
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?,?)",
                (digest(token), u["id"], csrf, time.time() + 8 * 3600),
            )
            store.audit(db, u["id"], "LOGIN", {})
        response.set_cookie(
            "motor_session",
            token,
            httponly=True,
            samesite="strict",
            secure=os.environ.get("MOTOR_SECURE_COOKIE") == "1",
            max_age=8 * 3600,
        )
        return {"id": u["id"], "role": u["role"], "csrf": csrf}

    @app.get("/api/me")
    def me(user=Depends(actor)):
        return user

    @app.post("/api/logout")
    def logout(request: Request, response: Response, user=Depends(actor)):
        with store.connect() as db:
            db.execute(
                "DELETE FROM sessions WHERE token=?",
                (digest(request.cookies.get("motor_session", "")),),
            )
            store.audit(db, user["id"], "LOGOUT", {})
        response.delete_cookie("motor_session")
        return {"ok": True}

    @app.get("/api/users")
    def users(user=Depends(roles("admin"))):
        with store.connect() as db:
            return [dict(r) for r in db.execute("SELECT id,role,active FROM users ORDER BY id")]

    @app.post("/api/users", status_code=201)
    def create_user(body: UserInput, user=Depends(roles("admin"))):
        with store.connect() as db:
            if db.execute("SELECT 1 FROM users WHERE id=?", (body.username,)).fetchone():
                raise HTTPException(409, "Usuario existente")
            db.execute(
                "INSERT INTO users(id,password,role) VALUES(?,?,?)",
                (body.username, password_hash(body.password), body.role),
            )
            store.audit(db, user["id"], "USER_CREATED", {"id": body.username, "role": body.role})
        return {"id": body.username, "role": body.role}

    @app.post("/api/users/{username}/disable")
    def disable(username: str, user=Depends(roles("admin"))):
        if username == user["id"]:
            raise HTTPException(400, "No puedes desactivar tu propia sesión")
        with store.connect() as db:
            db.execute("UPDATE users SET active=0 WHERE id=?", (username,))
            db.execute("DELETE FROM sessions WHERE user_id=?", (username,))
            store.audit(db, user["id"], "USER_DISABLED", {"id": username})
        return {"ok": True}

    @app.get("/api/sources")
    def sources(user=Depends(actor)):
        with store.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT s.id,s.kind,s.name,s.sha,s.created,COUNT(r.id) AS rows,SUM(r.error IS NOT NULL) AS invalid FROM sources s JOIN records r ON r.source_id=s.id GROUP BY s.id ORDER BY s.created DESC"
                )
            ]

    @app.post("/api/sources")
    async def upload(
        kind: str = Form(...),
        sheet: str = Form(""),
        file: UploadFile = File(...),
        user=Depends(roles("admin", "analyst")),
    ):
        if kind == "TARIFAS" and user["role"] != "admin":
            raise HTTPException(403, "Las tarifas documentadas requieren administrador")
        data = await file.read(100 * 1024 * 1024 + 1)
        if len(data) > 100 * 1024 * 1024:
            raise HTTPException(413, "Límite de archivo: 100 MB")
        try:
            with store.connect() as db:
                return import_source(
                    store, db, kind, file.filename or "", data, user["id"], sheet or None
                )
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/sources/{sid}/records")
    def source_records(sid: str, offset: int = 0, limit: int = 100, user=Depends(actor)):
        with store.connect() as db:
            rows = db.execute(
                "SELECT id,row_no,data,error FROM records WHERE source_id=? ORDER BY row_no LIMIT ? OFFSET ?",
                (sid, min(max(limit, 1), 500), max(offset, 0)),
            )
            return [dict(r) | {"data": json.loads(r["data"])} for r in rows]

    @app.get("/api/evidence/{rid}")
    def evidence(rid: str, user=Depends(actor)):
        with store.connect() as db:
            r = db.execute(
                "SELECT r.*,s.kind,s.sha,s.name FROM records r JOIN sources s ON s.id=r.source_id WHERE r.id=?",
                (rid,),
            ).fetchone()
            if not r:
                raise HTTPException(404, "Evidencia no encontrada")
            store.audit(db, user["id"], "EVIDENCE_VIEWED", {"record": rid})
            result = dict(r)
            result["data"] = json.loads(r["data"])
            result["raw"] = json.loads(r["raw"])
            return result

    @app.get("/api/runs")
    def runs(user=Depends(actor)):
        with store.connect() as db:
            return [
                dict(r) | {"config": json.loads(r["config"])}
                for r in db.execute(
                    "SELECT id,created,actor,config FROM runs ORDER BY created DESC LIMIT 100"
                )
            ]

    @app.post("/api/runs", status_code=201)
    def run(body: RunInput, user=Depends(roles("admin", "analyst"))):
        config = body.model_dump()
        try:
            date.fromisocalendar(body.year, body.week, 1)
        except ValueError as exc:
            raise HTTPException(422, "Semana ISO inválida") from exc
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for sid in body.sources:
                if not db.execute("SELECT 1 FROM sources WHERE id=?", (sid,)).fetchone():
                    raise HTTPException(422, "Fuente inexistente")
                if db.execute(
                    "SELECT 1 FROM records WHERE source_id=? AND error IS NOT NULL LIMIT 1", (sid,)
                ).fetchone():
                    raise HTTPException(
                        422,
                        "Fuente con filas inválidas: crea una versión corregida; original conservado",
                    )
            kinds = {
                r["kind"]
                for r in db.execute("SELECT id,kind FROM sources")
                if r["id"] in body.sources
            }
            if not {"RV", "PASOS", "FLOTA"} <= kinds:
                raise HTTPException(422, "Selecciona al menos RV, Pasos y Flota")
            result = reconcile(store, db, config)
            runid = uid()
            db.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?)",
                (runid, now(), user["id"], dumps(config), dumps(result)),
            )
            store.audit(
                db,
                user["id"],
                "RUN_CREATED",
                {"id": runid, "config": config, "result_hash": digest(result)},
            )
        return {"id": runid, "totals": result["totals"], "issues": result["issues"]}

    def load_run(db, runid):
        r = db.execute("SELECT * FROM runs WHERE id=?", (runid,)).fetchone()
        if not r:
            raise HTTPException(404, "Ejecución no encontrada")
        return json.loads(r["result"])

    @app.get("/api/runs/{runid}")
    def result(runid: str, user=Depends(actor)):
        with store.connect() as db:
            r = load_run(db, runid)
            return {k: v for k, v in r.items() if k != "rows"} | {"row_count": len(r["rows"])}

    @app.get("/api/runs/{runid}/rows")
    def result_rows(
        runid: str,
        q: str = "",
        state: str = "",
        offset: int = 0,
        limit: int = 100,
        user=Depends(actor),
    ):
        with store.connect() as db:
            rows = load_run(db, runid)["rows"]
        rows = [
            r
            for r in rows
            if (not q or q.lower() in dumps(r).lower())
            and (not state or state in r["state"] or state in r["blocks"])
        ]
        return {
            "total": len(rows),
            "rows": rows[max(0, offset) : max(0, offset) + min(max(limit, 1), 500)],
        }

    @app.get("/api/proposals")
    def proposals(user=Depends(actor)):
        with store.connect() as db:
            return [
                dict(r) | {"payload": json.loads(r["payload"])}
                for r in db.execute(
                    "SELECT p.*,d.approved,d.actor AS reviewer,d.reason AS decision_reason FROM proposals p LEFT JOIN decisions d ON d.proposal_id=p.id ORDER BY p.created DESC LIMIT 300"
                )
            ]

    def validate_proposal(db, body, decision=False):
        r = db.execute(
            "SELECT r.*,s.kind FROM records r JOIN sources s ON s.id=r.source_id WHERE r.id=?",
            (body.rv_id,),
        ).fetchone()
        if not r or r["kind"] != "RV" or r["error"]:
            raise HTTPException(422, "Selecciona un registro RV válido")
        rv = json.loads(r["data"])
        physical = amount(rv["physical_km"])
        current = store.approved(db).get(body.rv_id)
        if (current["id"] if current else None) != body.parent:
            raise HTTPException(
                409, "Existe otra versión aprobada: actualiza el padre antes de corregir"
            )
        if body.resolution == "reject" and body.segments:
            raise HTTPException(422, "Rechazo debe dejar segmentos vacíos")
        if body.resolution == "validate" and not body.segments:
            raise HTTPException(422, "Validación requiere segmentos")
        ranges = []
        used = set()
        for s in body.segments:
            try:
                a, b = Decimal(s.start_km), Decimal(s.end_km)
                if not a.is_finite() or not b.is_finite() or not 0 <= a < b <= physical:
                    raise ValueError()
            except Exception as exc:
                raise HTTPException(
                    422, "Segmentos requieren 0 ≤ inicio < fin ≤ km físico RV"
                ) from exc
            if any(a < y and b > x for x, y in ranges):
                raise HTTPException(422, "Segmentos solapados: exclusividad por km")
            ranges.append((a, b))
            if bool(s.departure) != bool(s.arrival):
                raise HTTPException(422, "El segmento requiere ambas horas o ninguna")
            if s.departure:
                try:
                    clock(s.departure)
                    clock(s.arrival)
                    bounds = interval(rv)
                    sbounds = interval(s.model_dump())
                    if not bounds or not sbounds:
                        raise ValueError()
                    x, y = sbounds
                    if x < bounds[0] and bounds[1] >= 1440:
                        x += 1440
                        y += 1440
                    if not bounds[0] <= x < y <= bounds[1]:
                        raise ValueError()
                except ValueError as exc:
                    raise HTTPException(422, "Horas de segmento fuera del intervalo RV") from exc
            for eid in s.evidence_ids:
                er = db.execute("SELECT source_id,error FROM records WHERE id=?", (eid,)).fetchone()
                if not er or er["error"]:
                    raise HTTPException(422, "Referencia de evidencia inválida")
                used.add(eid)
        for eid in body.cleared_events:
            if not db.execute(
                "SELECT 1 FROM records r JOIN sources s ON s.id=r.source_id WHERE r.id=? AND s.kind IN ('APOYOS','DESINC') AND r.error IS NULL",
                (eid,),
            ).fetchone():
                raise HTTPException(422, "Evento de regularización inválido")
        # Una evidencia física aprobada no puede respaldar dos RV vigentes.
        for other_id, p in store.approved(db).items():
            if other_id == body.rv_id:
                continue
            other_used = {e for s in p["payload"]["segments"] for e in s["evidence_ids"]}
            if used & other_used:
                raise HTTPException(409, "Evidencia ya atribuida a otro RV aprobado")
        return rv

    @app.post("/api/proposals", status_code=201)
    def propose(body: Proposal, user=Depends(roles("admin", "analyst"))):
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            validate_proposal(db, body)
            pid = uid()
            payload = body.model_dump(exclude={"rv_id", "parent", "reason", "evidence"})
            db.execute(
                "INSERT INTO proposals VALUES(?,?,?,?,?,?,?,?)",
                (
                    pid,
                    now(),
                    user["id"],
                    body.rv_id,
                    body.parent,
                    dumps(payload),
                    body.reason,
                    body.evidence,
                ),
            )
            store.audit(
                db,
                user["id"],
                "PROPOSAL_CREATED",
                {"id": pid, "rv_id": body.rv_id, "parent": body.parent},
            )
        return {"id": pid}

    @app.post("/api/proposals/{pid}/decision")
    def decide(pid: str, body: Decision, user=Depends(roles("admin", "reviewer"))):
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            p = db.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
            if not p:
                raise HTTPException(404, "Propuesta no encontrada")
            if p["actor"] == user["id"]:
                raise HTTPException(403, "Debe decidir otra persona: separación de funciones")
            if db.execute("SELECT 1 FROM decisions WHERE proposal_id=?", (pid,)).fetchone():
                raise HTTPException(409, "Propuesta ya decidida")
            if body.approved:
                validate_proposal(
                    db,
                    Proposal(
                        rv_id=p["rv_id"],
                        parent=p["parent"],
                        reason=p["reason"],
                        evidence=p["evidence"],
                        **json.loads(p["payload"]),
                    ),
                    True,
                )
            db.execute(
                "INSERT INTO decisions VALUES(?,?,?,?,?,?)",
                (uid(), pid, user["id"], now(), int(body.approved), body.reason),
            )
            store.audit(db, user["id"], "PROPOSAL_DECIDED", {"id": pid, **body.model_dump()})
        return {"ok": True, "rerun_required": True}

    @app.get("/api/audit")
    def audit(offset: int = 0, user=Depends(roles("admin", "reviewer"))):
        with store.connect() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM audit ORDER BY seq")]
        prev = "0" * 64
        valid = True
        for r in rows:
            valid &= r["previous"] == prev and r["hash"] == digest(
                [r["created"], r["actor"], r["event"], r["payload"], prev]
            )
            prev = r["hash"]
        return {
            "chain_valid": bool(valid),
            "count": len(rows),
            "rows": rows[max(0, offset) : max(0, offset) + 200],
        }

    @app.get("/api/runs/{runid}/export/{fmt}")
    def export(runid: str, fmt: Literal["csv", "xlsx", "json"], user=Depends(actor)):
        with store.connect() as db:
            r = load_run(db, runid)
            store.audit(db, user["id"], "EXPORT", {"id": runid, "format": fmt})
        headers = [
            "id",
            "date",
            "line",
            "route",
            "journey",
            "trip",
            "planned_company",
            "real_company",
            "economic_company",
            "vehicle",
            "real_type",
            "planned_km",
            "physical_km",
            "physical_counted",
            "covered_km",
            "eligible_km",
            "rate",
            "estimated_amount",
            "state",
            "blocks",
            "approved_proposal",
        ]

        def safe(v):
            if isinstance(v, (dict, list)):
                v = dumps(v)
            v = "" if v is None else str(v)
            return "'" + v if v.startswith(("=", "+", "-", "@", "\t", "\r")) else v

        if fmt == "json":
            content = dumps(r).encode()
            mime = "application/json"
        elif fmt == "csv":
            stream = io.StringIO()
            writer = csv.writer(stream)
            writer.writerow(headers)
            writer.writerows([[safe(row.get(h)) for h in headers] for row in r["rows"]])
            content = stream.getvalue().encode("utf-8-sig")
            mime = "text/csv"
        else:
            from openpyxl import Workbook

            book = Workbook()
            ws = book.active
            ws.title = "Viajes"
            ws.append(headers)
            for row in r["rows"]:
                ws.append([safe(row.get(h)) for h in headers])
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for title, rows in [
                ("Desgloses", r["groups"]),
                ("Resumen", [r["totals"]]),
                (
                    "Advertencias",
                    [{"liquidation": r["liquidation"], "acceptance": r["pilot_acceptance"]}],
                ),
                ("Fuentes", [{"id": s} for s in r["config"]["sources"]]),
            ]:
                sheet = book.create_sheet(title)
                if rows:
                    cols = list(rows[0])
                    sheet.append(cols)
                    for row in rows:
                        sheet.append([safe(row.get(h)) for h in cols])
                sheet.freeze_panes = "A2"
            buffer = io.BytesIO()
            book.save(buffer)
            content = buffer.getvalue()
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return Response(
            content,
            media_type=mime,
            headers={"Content-Disposition": f'attachment; filename="propuesta_{runid}.{fmt}"'},
        )

    return app


app = create_app()
