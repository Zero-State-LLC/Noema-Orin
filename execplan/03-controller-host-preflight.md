# T5a: Credential-free Controller-host preflight

This living ExecPlan implements [SPEC-T5A.md](../SPEC-T5A.md), [spec #16](https://github.com/Zero-State-LLC/Noema-Orin/issues/16) and [ticket #17](https://github.com/Zero-State-LLC/Noema-Orin/issues/17). The preflight is local telemetry; physical qualification #5, live attach #4 and Spark writer authority #6 remain separately gated.

## Purpose / Big Picture

From the returned Orin host, an operator can run `python -m noema_orin.preflight` and receive a single non-identifying JSON record. The same command works on another machine but never asserts that it is a Jetson or ready for deployment. All observations are sanitized, absent ones are `NOT_COMPUTABLE`; no network or subprocess is used.

## Progress

- [x] (2026-10-31) Operator approved narrow T5a scope and one vertical-slice implementation ticket; spec #16 and ticket #17 published.
- [x] (2026-10-31) Wrote failing public-seam tests: `ModuleNotFoundError` for absent `noema_orin.preflight` on Python 3.14; then implemented probe protocol and exact receipt. The initial 36-test core suite passed locally on Python 3.10–3.13. After review-found RED regressions for raising attribute lookups and extra NUL terminators, the repaired 38-test core suite passed on each of Python 3.10–3.13.
- [x] (2026-10-31) Installed the package into isolated Python 3.10–3.13 environments outside the checkout; confirmed site-packages import and one safe CLI record on the macOS host. This is package portability, not Jetson evidence.
- [x] (2026-10-31) Added poisoned model/L4T-tail and bounded-read regressions; the initial 36-test suite passed locally on Python 3.10–3.13. Added installed-package preflight checks to each existing synthetic CI cell, including Ubuntu arm64. Subsequent exact-head hosted runs are recorded below.
- [x] (2026-10-31) Initial PR #18 head `70fe157bea26a6355946c4a8b05c21c43c243cb9` passed ten hosted jobs, but independent Standards and Spec reviews BLOCKED it: injected attribute access happened outside the fail-safe guard, and multiple trailing NULs were accepted as an exact device-label match. Added public-entry regression tests that reproduced both failures before repairing them. That initial CI and those reviews are historical, not clearance for the repaired head.
- [x] (2026-10-31) Second PR #18 head `12585390290c20b53141ce1520da9ba1dfc2bf96` passed ten hosted jobs and Standards review, but Spec review BLOCKED it: `MemTotal` with a newline between the key and value was accepted as valid RAM. Added a public-entry regression and observed RED on split-line and carriage-return cases before tightening the parser to horizontal whitespace. The second-head CI and Standards PASS are historical, not clearance for this repair.
- [x] (2026-10-31) Tightened the split-line `MemTotal` parser after a public-entry RED, and independently tested L4T whitespace/control-boundary near-matches RED before replacing broad `strip()` with at-most-one trailing LF. These repairs require fresh exact-head CI and reviews.
- [x] (2026-10-31) Third PR #18 head `0edd17baea5fd30470d046baa7792804dc85dae5` passed ten hosted jobs but both independent reviews BLOCKED it: Unicode decimal digits escaped the ASCII receipt grammar, and a malformed duplicate `MemTotal` was ignored. Public-entry regressions reproduced both failures before replacing `\d` with `[0-9]` and counting raw key occurrences. An expanded parser sweep reproduced malformed OS-key duplicates too; the same fix now refuses them. Added a hostile-observation vocabulary regression. The third-head CI remains historical.
- [x] (2026-10-31) Ran 45 core tests per interpreter on Python 3.10–3.13 and installed-package preflight outside the checkout on macOS arm64 for the repaired tree. These local results do not replace hosted CI or device proof.
- [x] (2026-10-31) Fourth head `0795e413c839b846aedd3b713cb787c24a363db3` passed ten hosted jobs (run `41275073961`), including installed-package cells on Ubuntu x86_64 and arm64; both independent exact-head reviews BLOCKED it. A CR, NUL, Unicode separator or BOM before a second OS/RAM key hid the malformed duplicate from LF-anchored key counting. Reproduced at `run_preflight` with RED tests, then rejected control-bearing host text at the file-parser boundary (printable ASCII plus LF/TAB only; exact model-file NUL remains separate). The repaired local suite passed 47 tests on each Python 3.10–3.13, including an ASCII/control-code sweep. Isolated installed-package CLI passed outside checkout on macOS arm64 across those interpreters. Fourth-head CI is historical, not clearance for the repair.
- [x] (2026-10-31) Final PR #18 head `4388b1825ee0d3920eb4ec5c40e7972ed925c7f5` passed all ten hosted jobs in run `41275393841`, including installed-package preflight on Ubuntu x86_64 and arm64. Two independent exact-head delegated reviews returned PASS with no blocker; these were not formal GitHub approvals. Nonblocking follow-ups: independently pin `source_sha` in the installed CI assertion and assert the complete record in the subprocess CLI test.
- [x] (2026-10-31) Merged PR #18 with `--merge --delete-branch --match-head-commit` at merge SHA `d2abd94c21d5ecd6baaef85aca3e6867420516a2`. Verified remote `main` and clean fast-forwarded local `main`; issue #17 closed, while #4–#6 and spec #16 remained open at verification. Post-merge run `41275586379` passed all ten jobs on that exact merge SHA. This is package/synthetic evidence, not physical Orin qualification.

- [x] (2026-10-31) Closed bounded spec issue #16 after verifying PRs #18–#19 and the post-merge main CI; this does not complete physical qualification #5.
- [x] (2026-10-31) On a separate branch, strengthened the subprocess CLI test to assert the complete key set and allowlisted vocabulary, with an injected extra-field mutation proven to fail; independently pinned the installed-preflight CI `source_sha` literal and exercised its actual step against a clean installed package, wrong pin, and extra-field mutation. The latter probe adapted Ubuntu-only expectations to the local macOS arm64 host. PR #20 head `2acbea412212e78d5f6e0522e0d7e32841e4fcbe` passed all ten hosted jobs in run `41276606015`; its exact-head Spec review passed, while Standards blocked stale status text in this plan. Those checks and reviews are historical for this documentation repair; its new head requires fresh CI and review.

## Surprises & Discoveries

- A method *lookup* can raise before a guarded call begins; the existing raising-method test covered invocation only. Guard the lookup and invocation together.
- `rstrip("\\x00")` removes arbitrarily many NULs; the candidate label must accept at most one file terminator.
- In regexes over multiline host files, `\\s*` can consume newline and carriage-return separators; match only horizontal whitespace for one-line `MemTotal` observations.

## Decision Log

- Decision: Preflight has its own entry module and probe seam; do not alter synthetic Controller receipts or client adapter. Rationale: different evidence scope and failure behavior. 2026-10-31/Bob.
- Decision: Output never echoes raw observations. Rationale: even apparently safe local model or release strings may contain identifiers. 2026-10-31/Bob.

## Outcomes & Retrospective

T5a local preflight merged via PR #18 at reviewed head `4388b1825ee0d3920eb4ec5c40e7972ed925c7f5`; merge SHA `d2abd94c21d5ecd6baaef85aca3e6867420516a2`. Exact-head CI run `41275393841` and post-merge main run `41275586379` each passed ten jobs. Two independent delegated exact-head reviews returned PASS, not formal GitHub approvals. Issue #17 closed; bounded spec #16 was closed after PRs #18–#19 and the post-merge checks. Live attach #4, physical qualification #5, and offline Spark writer authority #6 remain open. No returned board was measured; hosted arm64 and local macOS checks establish packaging and synthetic behavior only.

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
