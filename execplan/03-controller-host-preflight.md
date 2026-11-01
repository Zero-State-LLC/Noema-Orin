# T5a: Credential-free Controller-host preflight

This living ExecPlan implements [SPEC-T5A.md](../SPEC-T5A.md), [spec #16](https://github.com/Zero-State-LLC/Noema-Orin/issues/16) and [ticket #17](https://github.com/Zero-State-LLC/Noema-Orin/issues/17). The preflight is local telemetry; physical qualification #5, live attach #4 and Spark writer authority #6 remain separately gated.

## Purpose / Big Picture

From the returned Orin host, an operator can run `python -m noema_orin.preflight` and receive a single non-identifying JSON record. The same command works on another machine but never asserts that it is a Jetson or ready for deployment. All observations are sanitized, absent ones are `NOT_COMPUTABLE`; no network or subprocess is used.

## Progress

- [x] (2026-10-31) Operator approved narrow T5a scope and one vertical-slice implementation ticket; spec #16 and ticket #17 published.
- [ ] Write failing public-seam and CLI behavior tests.
- [ ] Implement and document bounded local probe and allowlisted receipt.
- [ ] Run local and hosted installed-package matrices, obtain exact-head reviews.
- [ ] Merge and record post-merge evidence without closing #4–#6.

## Surprises & Discoveries

None yet.

## Decision Log

- Decision: Preflight has its own entry module and probe seam; do not alter synthetic Controller receipts or client adapter. Rationale: different evidence scope and failure behavior. 2026-10-31/Bob.
- Decision: Output never echoes raw observations. Rationale: even apparently safe local model or release strings may contain identifiers. 2026-10-31/Bob.

## Outcomes & Retrospective

Pending tests and device evidence. A passing preflight is not a passing physical-device qualification.

## Context and Orientation

`src/noema_orin/receipts.py` pins the Specs SHA. `src/noema_orin/__main__.py` and `runner.py` implement only synthetic dry-run. `src/noema_orin/official_client.py` is optional loopback. The new `preflight.py` is independent of both paths. `docs/ORIN-8GB-PORT.md` holds the day-one steps; `.github/workflows/ci.yml` runs Python 3.10–3.13 x86 and arm64 jobs. Spec 014 in Noema-Specs remains SPECULATIVE.

## Plan of Work

Write a fake-probe test that supplies Orin-like observations, asserts the exact finite receipt, and fails while the module is absent. Add poisoned/malformed and raising-probe cases. Then implement a stdlib-only real probe reading bounded local files and metadata, with a narrow injected probe method for each observation. Normalize architecture and OS to finite sets, constrained L4T and versions to numeric grammars, model to one recognized candidate family, and numeric memory/storage into coarse buckets. Catch probe failures per field; never include raw error strings. Emit a single JSON line from the module entry point and keep stderr empty. Extend existing installed-package CI from outside source checkout and update the port packet. Do not contact a server or select a model.

## Concrete Steps

From repository root, run `PYTHONPATH=src python -m unittest discover -s tests -p 'test_preflight.py' -v` for RED and GREEN. Run complete tests on available 3.10–3.13 interpreters. `python -m pip install .` in a clean environment and execute `python -m noema_orin.preflight` outside checkout; compare import origins to the installed site-packages. Hosted CI performs installed assertions on both Ubuntu x86_64 and arm64. Use `git diff --check` before commit.

## Validation and Acceptance

The receipt contains only fixed keys, finite categories, strict numeric tokens and coarse capacity buckets. Exceptions and injected secrets never reach stdout/stderr. Exit 0 only reports inspection completion. Synthetic CLI and optional-client suites retain their independent checks. A CI arm64 result remains a portability check, not Jetson evidence. #4–#6 stay open.

## Idempotence and Recovery

Repeated inspection reads local state only; it makes no persistent changes. Missing or malformed files yield `NOT_COMPUTABLE`. A failure to install the package is a blocker, not reason to use a source-tree fallback. If model strings on the board differ from the assumed allowlist, mark unknown and revise under review; do not silently widen the acceptance claim.

## Artifacts and Notes

Local test/CI receipts and exact revisions will be entered as observed, not predicted.

## Interfaces and Dependencies

`run_preflight(probe=None) -> dict[str, str]` accepts an injected read-only probe for tests; `main() -> int` prints the record. Python >=3.10 standard library only. No client import, credentials, subprocess or network.

## Change note

2026-10-31: Initial plan; scope excludes real-world attach and physical acceptance.
