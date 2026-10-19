"""Motor determinista. El resultado es una propuesta revisable, nunca una liquidación."""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from .importers import clock, key
from .store import digest

VERSION = "1.0.0"
D = Decimal


def amount(v):
    return D(str(v)) if v is not None else D(0)


def identity(r):
    return digest(
        {
            k: r.get(k)
            for k in (
                "date",
                "route",
                "journey",
                "trip",
                "planned_company",
                "vehicle",
                "planned_departure",
                "departure",
                "arrival",
                "planned_km",
                "physical_km",
            )
        }
    )


def interval(r):
    a, b = clock(r.get("departure")), clock(r.get("arrival"))
    if a is None or b is None:
        return None
    if b < a:
        b += 1440
    return a, b


def candidate(p, r):
    times = [clock(p["checkpoints"][k]) for k in p["checkpoint_order"]]
    if len(times) < 2 or p["date"] != r["date"] or p["vehicle"] != r["vehicle"]:
        return False
    if p["journey"] and r["journey"] and p["journey"] != r["journey"]:
        return False
    bounds = interval(r)
    if not bounds or bounds[1] - bounds[0] > 240:
        return False
    a, b = bounds
    times = [t + 1440 if t < a - 5 else t for t in times]
    monotonic = all(x <= y for x, y in zip(times, times[1:], strict=False)) or all(
        x >= y for x, y in zip(times, times[1:], strict=False)
    )
    return monotonic and len(set(times)) >= 2 and all(a - 5 <= t <= b + 5 for t in times)


def event_overlaps(e, r):
    if e["vehicle"] != r["vehicle"] and (not e["journey"] or e["journey"] != r["journey"]):
        return False
    bounds = interval(r)
    if not bounds:
        return e["date"] == r["date"]
    base = datetime.fromisoformat(r["date"])
    start = datetime.fromisoformat(e["date"]) + timedelta(minutes=clock(e["time"]))
    end = datetime.fromisoformat(e["end_date"] or e["date"]) + timedelta(
        minutes=clock(e["end_time"]) if e["end_time"] else 1440
    )
    if end < start:
        end += timedelta(days=1)
    return start <= base + timedelta(minutes=bounds[1]) and end >= base + timedelta(
        minutes=bounds[0]
    )


def reconcile(store, db, config):
    selected = set(config["sources"])

    def records(kind):
        return [r for r in store.records(db, kind) if r["source_id"] in selected]

    start = date.fromisocalendar(config["year"], config["week"], 1).isoformat()
    end = date.fromisocalendar(config["year"], config["week"], 7).isoformat()
    rv_all = records("RV")
    rv = [r for r in rv_all if r["line"] == config["line"] and start <= r["date"] <= end]
    fleet, tariffs = records("FLOTA"), records("TARIFAS")
    pasos = records("PASOS")
    events = records("APOYOS") + records("DESINC")
    approvals = store.approved(db)
    selected_records = {
        row["id"]
        for row in db.execute("SELECT id,source_id FROM records")
        if row["source_id"] in selected
    }
    duplicate_counts = Counter(identity(r) for r in rv)
    fleet_index = defaultdict(list)
    for f in fleet:
        fleet_index[f["vehicle"]].append(f)
    rv_index = defaultdict(list)
    for r in rv:
        rv_index[(r["date"], r["vehicle"])].append(r)
    links = defaultdict(list)
    reverse = defaultdict(list)
    for p in pasos:
        for r in rv_index[(p["date"], p["vehicle"])]:
            if candidate(p, r):
                links[r["id"]].append(p)
                reverse[p["id"]].append(r["id"])
    conflicts = set()
    for group in rv_index.values():
        ordered = sorted([r for r in group if interval(r)], key=lambda r: interval(r)[0])
        for i, r in enumerate(ordered):
            for other in ordered[i + 1 :]:
                if interval(other)[0] >= interval(r)[1]:
                    break
                if (
                    identity(r) != identity(other)
                    and amount(r["physical_km"]) > 0
                    and amount(other["physical_km"]) > 0
                ):
                    conflicts.update((r["id"], other["id"]))
    output = []
    seen = set()
    planned_seen = set()
    totals = defaultdict(Decimal)
    for r in rv:
        blocks = []
        alerts = []
        rid = r["id"]
        fingerprint = identity(r)
        duplicate = fingerprint in seen
        seen.add(fingerprint)
        programmed = r["planned_km"] is not None and bool(r["planned_departure"])
        # La asignación del económico nunca integra la clave de programación.
        plan_key = digest(
            [
                r[k]
                for k in (
                    "date",
                    "route",
                    "planned_company",
                    "journey",
                    "trip",
                    "planned_departure",
                    "planned_km",
                )
            ]
        )
        plan_duplicate = programmed and plan_key in planned_seen
        if programmed:
            planned_seen.add(plan_key)
        if programmed and not plan_duplicate:
            totals["planned_km"] += amount(r["planned_km"])
        if not duplicate:
            totals["physical_km"] += max(D(0), amount(r["physical_km"]))
        if duplicate_counts[fingerprint] > 1:
            blocks.append("DUPLICADO_RV")
        if plan_duplicate:
            alerts.append("PROGRAMACION_REPETIDA_REVISAR")
        if r["physical_km"] is None:
            blocks.append("KM_FISICO_NO_CAPTURADO")
        elif amount(r["physical_km"]) < 0:
            blocks.append("KM_NEGATIVO_REVISAR")
        if rid in conflicts:
            blocks.append("SOLAPAMIENTO_VEHICULO")
        if not r["planned_company"]:
            blocks.append("EMPRESA_PROGRAMADA_NO_DETERMINADA")
        if not r["journey"]:
            alerts.append("JORNADA_NO_DETERMINADA")
        if r["dates"]["boundary_pending"]:
            blocks.append("BORDE_DIA_OPERATIVO_0300_0320")
        if "CANCEL" in key(r["status"]) and amount(r["physical_km"]) > 0:
            alerts.append("CANCELADA_CON_KM_FISICO")
        if "L01A21" in r["route"]:
            alerts.append("TRASLADO_PROGRAMADO_VALIDABLE")
        fs = [f for f in fleet_index[r["vehicle"]] if f["valid_from"] <= r["date"] <= f["valid_to"]]
        real_company = fs[0]["company"] if len(fs) == 1 else ""
        real_type = fs[0]["vehicle_type"] if len(fs) == 1 else ""
        if len(fs) != 1:
            blocks.append("FLOTA_AUSENTE_O_AMBIGUA")
        cross = bool(
            real_company and r["planned_company"] and key(real_company) != key(r["planned_company"])
        )
        ev = [e for e in events if event_overlaps(e, r)]
        proposal = approvals.get(rid)
        payload = proposal["payload"] if proposal else {}
        referenced = {
            eid for segment in payload.get("segments", []) for eid in segment["evidence_ids"]
        }
        referenced.update(payload.get("cleared_events", []))
        if not referenced <= selected_records:
            blocks.append("EVIDENCIA_AUTORIZADA_FUERA_DE_FUENTES")
        cleared = set(payload.get("cleared_events", []))
        pending_events = [e["id"] for e in ev if e["id"] not in cleared]
        if pending_events:
            blocks.append("EVENTO_CCO_LOCALIZADO_PENDIENTE")
        if cross and not payload.get("economic_company"):
            blocks.append("INTEREMPRESA_ATRIBUCION_PENDIENTE")
        economic_company = payload.get("economic_company") or real_company
        ts = [
            t
            for t in tariffs
            if key(t["company"]) == key(economic_company)
            and key(t["vehicle_type"]) == key(real_type)
            and t["line"] == config["line"]
            and t["valid_from"] <= r["date"] <= t["valid_to"]
        ]
        rate = ts[0]["rate"] if len(ts) == 1 else None
        if len(ts) != 1:
            blocks.append("TARIFA_AUSENTE_O_VIGENCIA_AMBIGUA")
        candidates = links[rid]
        unique = [p for p in candidates if len(reverse[p["id"]]) == 1]
        if len(candidates) != 1 or len(unique) != 1:
            alerts.append("VINCULO_PASOS_AMBIGUO_O_AUSENTE")
        if candidates and any(
            p["physical_km"] is not None
            and abs(amount(p["physical_km"]) - amount(r["physical_km"])) > D("0.011")
            for p in candidates
        ):
            alerts.append("DIFERENCIA_KM_PASOS_RV")
        segments = payload.get("segments", [])
        covered = sum((amount(s["end_km"]) - amount(s["start_km"]) for s in segments), D(0))
        if not proposal:
            blocks.append("COBERTURA_NO_AUTORIZADA")
        if proposal and payload.get("resolution") == "reject":
            blocks.append("COBERTURA_RECHAZADA_AUTORIZADA")
        eligible = D(0)
        segment_ledger = []
        global_blocks = [b for b in blocks if b != "EVENTO_CCO_LOCALIZADO_PENDIENTE"]
        for segment in segments:
            sr = dict(r)
            if segment.get("departure") and segment.get("arrival"):
                sr.update(departure=segment["departure"], arrival=segment["arrival"])
                # Horas después de medianoche pertenecen al día siguiente del RV.
                if clock(sr["departure"]) < clock(r["departure"]) and interval(r)[1] >= 1440:
                    sr["date"] = (date.fromisoformat(r["date"]) + timedelta(days=1)).isoformat()
            held = [e["id"] for e in ev if e["id"] not in cleared and event_overlaps(e, sr)]
            km = amount(segment["end_km"]) - amount(segment["start_km"])
            credit = km if not global_blocks and not held and not duplicate else D(0)
            eligible += credit
            segment_ledger.append(dict(segment, held_events=held, eligible_km=str(credit)))
        if D(0) < eligible < covered:
            alerts.append("COBERTURA_PARCIALMENTE_BLOQUEADA")
        estimate = (eligible * amount(rate)).quantize(D("0.01"))
        totals["covered_km"] += covered if not duplicate else D(0)
        totals["eligible_km"] += eligible
        totals["estimated_amount"] += estimate
        output.append(
            {
                **r,
                "fingerprint": fingerprint,
                "programmed": programmed,
                "physical_counted": not duplicate,
                "planned_counted": programmed and not plan_duplicate,
                "real_company": real_company,
                "real_type": real_type,
                "economic_company": economic_company,
                "rate": rate,
                "covered_km": str(covered),
                "eligible_km": str(eligible),
                "estimated_amount": str(estimate),
                "blocks": blocks,
                "alerts": alerts,
                "events": [e["id"] for e in ev],
                "candidates": [p["id"] for p in candidates],
                "segments": segments,
                "segment_ledger": segment_ledger,
                "approved_proposal": proposal["id"] if proposal else None,
                "state": "ELEGIBLE_PROPUESTA"
                if eligible > 0
                else "PENDIENTE"
                if blocks
                else "SIN_KM_ELEGIBLE",
            }
        )
    groups = {}
    for r in output:
        k = tuple(
            r.get(x, "")
            for x in ("line", "planned_company", "real_company", "real_type", "journey", "vehicle")
        )
        g = groups.setdefault(
            k,
            {
                "line": k[0],
                "planned_company": k[1],
                "real_company": k[2],
                "real_type": k[3],
                "journey": k[4],
                "vehicle": k[5],
                "trips": 0,
                "planned_km": D(0),
                "physical_km": D(0),
                "covered_km": D(0),
                "eligible_km": D(0),
                "estimated_amount": D(0),
            },
        )
        g["trips"] += 1
        for field in ("planned_km", "physical_km", "covered_km", "eligible_km", "estimated_amount"):
            count = r["planned_counted"] if field == "planned_km" else r["physical_counted"]
            g[field] += amount(r.get(field)) if count else D(0)
    issues = Counter(b for r in output for b in r["blocks"])
    return dict(
        engine_version=VERSION,
        config=config,
        scope={
            "from": start,
            "to": end,
            "date_basis": "fecha declarada; ambas adscripciones calculadas sin reasignar silenciosamente",
        },
        liquidation="NO_AUTORIZADA",
        pilot_acceptance="PENDIENTE_VALIDACION_USUARIO",
        totals={
            k: str(totals[k])
            for k in ("planned_km", "physical_km", "covered_km", "eligible_km", "estimated_amount")
        },
        rows=output,
        groups=[
            {k: str(v) if isinstance(v, D) else v for k, v in g.items()} for g in groups.values()
        ],
        issues=dict(issues),
        source_rows=len(rv_all),
        excluded_rows=len(rv_all) - len(rv),
        supplemental={
            "circuitos": len(records("CIRCUITOS")),
            "apoyos": len(records("APOYOS")),
            "desincorporaciones": len(records("DESINC")),
        },
        notes=[
            "Circuitos son evidencia complementaria: nunca se suman de nuevo al RV.",
            "Sin captura o sin cobertura no equivale a incumplimiento.",
            "Llegada SAE es marca temporal; no prueba llegada a terminal.",
            "Estimaciones económicas sujetas a aprobación; no existe función de pago.",
        ],
    )
