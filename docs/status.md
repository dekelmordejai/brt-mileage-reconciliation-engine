# Implementation status and limits

The baseline demonstrates an executable local analysis/review workflow, not a production deployment or a validated financial model. The current public CI run is the authoritative software-check status.

| Capability | Status |
|---|---|
| Multi-format import, validation and provenance | Implemented and tested |
| Schedule, physical report and reviewed coverage separation | Implemented and tested |
| Versioned manual segment correction and second-person review | Implemented and tested |
| Localized holds, evidence exclusivity and overlapping vehicle detection | Implemented and tested |
| Date-effective actual-vehicle tariff proposals and blocked ambiguity | Implemented and tested |
| Sessions, roles, CSRF and hash-linked audit | Implemented and tested; not a security certification |
| Browser workflow, Excel/CSV/JSON and installable package | Implemented and tested |
| Docker image construction and Python/browser CI | Reproducible checks; not a live hosted deployment |
| Automatic spatial reconstruction | Not implemented |
| General cross-company contractual treatment | No default rule; unresolved cases stay pending |
| Contractual rounding, settlement and organizational acceptance | Not implemented/validated |
| Enterprise identity, high availability, distributed processing | Outside demo scope |

The reviewed baseline contains 52 passing tests and 3 explicit skipped design questions. Skipped cases are not claimed as passing. Synthetic examples establish expected software behavior, not production accuracy, independent physical execution, savings or deployment adoption.

All actual operational materials, private case studies, historical references, institutional results, recordings, credentials and databases remain outside this public repository. The code snapshot and synthetic examples are sufficient to reproduce the public demonstration. No operational dataset is required or offered.
