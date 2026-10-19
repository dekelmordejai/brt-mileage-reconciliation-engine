# Source contracts

Only synthetic examples are distributed (`fixtures/synthetic.json` and `examples/synthetic/`). CSV uses UTF-8 or CP1252 and comma/semicolon delimiters. XLSX supports a selected sheet. JSON imports a list of objects. The original bytes and row values are preserved; normalized values are derived, not written over the source.

| Kind | Canonical fields |
|---|---|
| RV | date, route, journey, trip, planned_company, assigned_vehicle, vehicle, planned_departure, departure, arrival, planned_km, physical_km, status |
| PASOS | date, journey, vehicle, trip, physical_km, ordered station/checkpoint columns |
| FLOTA | vehicle, company, vehicle_type, optional valid_from / valid_to |
| CIRCUITOS | date, route, journey, vehicle, departure, arrival, physical_km |
| APOYOS | date, time, optional end_date / end_time, vehicle, journey, company, line, km2, station, reason |
| DESINC | date, time, optional end_date / end_time, vehicle, journey, replacement, line, km, reason |
| TARIFAS | line, company, vehicle_type, valid_from, valid_to, rate, reference |
| DISTANCIAS | route, start, end, km |

Absence markers do not imply zero. In the support adapter, KM2=0 means uncaptured. Decimal accepts one decimal separator; ambiguous mixed separators are rejected. Dates support ISO YYYY-MM-DD or DD/MM/YYYY, and times use HH:mm[:ss]. Invalid rows remain visible and block processing that source. Import a new corrected version instead of editing stored rows.

The conventional 03:20 boundary and provisional 03:00 assignment are explicit example-domain policies. Original declared dates are retained, and disagreement remains visible. They are not universal transit standards. Candidate tolerances are exploratory technical settings, not financial authorization thresholds.

The distance catalog can support a manual reviewed segment; automatic spatial reconstruction is not implemented. An open-ended fleet validity interval is a declared catalog assumption, not an independently verified assignment. See implementation limits before adapting to a real operation.

The interactive API specification is at `/docs` on the local running server. Writes require a role-authorized session and `X-CSRF-Token`; the token is delivered at login. Evidence and decisions retain source-row references in the audit history.
