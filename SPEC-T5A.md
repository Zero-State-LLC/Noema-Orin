# Spec: T5a credential-free Controller-host preflight

**Status:** Operator-approved for a local, read-only implementation only. This is a bounded preliminary slice of physical measurement ticket #5, not completion of #5. Authority: Noema-Specs `619d0674518761aa08462d3f5d5966a917259aa1`, Spec 014 remains SPECULATIVE. This spec alone does not authorize an isolated-world attach (#4), device qualification (#5), or Spark writing (#6).

## Problem Statement

Before the Jetson Orin Nano 8GB returns, an operator needs a repeatable, safe way to inspect its local host prerequisites. A manual checklist can accidentally leak identifiers or mistake an Ubuntu arm64 CI runner for the actual device. Neither the existing synthetic dry-run nor the official-client loopback test measures the board.

## Solution

Add a separate, stdlib-only `python -m noema_orin.preflight` command with a single injected, read-only host-probe boundary. It prints exactly one fixed-shape JSON receipt with only allowlisted categorical or bounded values; absent, malformed, or failing observations become `NOT_COMPUTABLE`. The receipt is local telemetry, never a readiness verdict. The existing Controller runner, synthetic CLI, receipt schema, and optional loopback adapter remain unchanged.

## User Stories

1. As an operator, I want one local command to inspect OS, CPU architecture, Python, L4T, RAM and free storage, so that I can prepare for board bring-up without running a Controller.
2. As an operator, I want official-client distribution availability and version reported without importing it or contacting a server, so that I can identify an interpreter mismatch safely.
3. As a reviewer, I want a receipt that never includes hostname, username, serial, MAC/IP, local paths, environment values, raw file contents or exception strings, so that a public log cannot expose device identity or credentials.
4. As an operator, I want missing and malformed observations to be `NOT_COMPUTABLE`, so that a CI runner cannot silently pass as physical Orin evidence.
5. As a maintainer, I want injected host probes to exercise the exact command behavior on synthetic Orin-like, non-Jetson, malformed and raising inputs, so that the tool is testable without the board.
6. As a future device operator, I want the receipt to leave model load, tokens/s, power, latency, and JetPack identity unmeasured, so that no model or device qualification is inferred.
7. As an operator, I want the current `hosted` synthetic dry-run and `offline-spark` refusal preserved, so that the inspection command cannot change NOEMA authority.

## Implementation Decisions

- The sole new test seam is the preflight entry function accepting one injected, read-only probe. The public command uses the real local probe; tests pass deterministic fake probes. Keep it separate from the Controller runner and its receipt contract.
- The real probe may use only Python's standard library, local `/etc/os-release`, `/etc/nv_tegra_release`, `/proc/device-tree/model`, `/proc/meminfo`, filesystem capacity of `/`, `platform.machine`, `sys.version_info`, and local package metadata for `noema-client`. It performs no subprocess or network operation and imports no optional client code.
- For parsed host text (`/etc/os-release`, `/etc/nv_tegra_release`, `/proc/meminfo`), accept only bounded printable ASCII with LF and TAB; reject control characters, CRLF, NUL, BOM and non-ASCII as malformed before parsing. The device-tree model is separate: its exact recognized label may have one terminating NUL only.
- Normalize all output into a literal allowlist: `machine` is one of `aarch64`, `x86_64`, `arm64` or `NOT_COMPUTABLE`; `os_id` is `ubuntu` or `NOT_COMPUTABLE`; `os_version` is `22.04`, `24.04` or `NOT_COMPUTABLE`; `l4t_release` is a constrained release/revision token or `NOT_COMPUTABLE`; `device_family` is `JETSON_ORIN_NANO_CANDIDATE` only for an exact recognized device-tree model or `NOT_COMPUTABLE`; Python/client versions are strict bounded numeric version tokens; RAM and free storage are coarse GiB buckets. Never serialize raw probe output. Candidate means a label reported by a local file, not authentication or qualification of the hardware.
- Emit exactly one JSON object to stdout, empty stderr and exit 0 when the inspection completes, even if some fields cannot be read. This exit code signals only that the inspection ran. Keep literal `claim_label=SPECULATIVE`, `evidence_scope=LOCAL_PREFLIGHT_ONLY`, `device_metrics=NOT_COMPUTABLE`, `jetpack_version=NOT_COMPUTABLE`, `model_load=NOT_COMPUTABLE`, `tokens_per_second=NOT_COMPUTABLE`, `power=NOT_COMPUTABLE`, and `command_latency=NOT_COMPUTABLE`. Fail-safe probe exceptions are not printed.
- The receipt carries the pinned Noema-Specs `source_sha`, not a runtime-observed Git commit; the eventual physical-device operator must record the exact Noema-Orin checkout separately.

## Testing Decisions

- Test behavior at the public preflight entry function and subprocess CLI only; do not test private parsing helpers. Fake probes supply fixed values and poison strings. Assert the complete allowlisted record, one line, empty stderr, and no subprocess/network side effects. Exercise a recognized model, a non-Jetson host, missing/malformed data, and raising probes; prove secrets do not echo.
- Run on Python 3.10–3.13, install the package into a clean environment and execute outside the checkout, then run Ubuntu x86_64 and arm64 CI. CI architecture is not JetPack evidence. Preserve the existing synthetic and optional-client test matrices.

## Out of Scope

No live isolated-world attach, real enrollment, #4 closure, #5 physical measurements or closure, #6 Spark writer decision, model selection/download/load, tokens/s or power measurement, network discovery, endpoint check, credential store, boot service, auto-start, privileged command, production deployment, PSR-1 promotion, world mutation, or firmware/OS installation.

## Further Notes

**OBSERVED:** `docs/ORIN-8GB-PORT.md` has an unexecuted day-one checklist; Noema-Orin `main` at `cdff03d30256074eb8ad99cbedf58a6ad22a2d75` has a synthetic runner and a loopback-only optional client. Noema-Specs Spec 014 remains SPECULATIVE with a writer-authority conflict. **INFERRED:** a local host-inspection receipt can make the later bring-up repeatable. **NOT_COMPUTABLE:** physical device identity, JetPack, model performance, and real-world compatibility until measured on the returned board. The operator approved this narrow preflight scope on 2026-10-31; no adjacent gate is lifted.
