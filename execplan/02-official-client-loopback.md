# Prove the pinned official Controller client on loopback without live admission

This ExecPlan is a living document. Update Progress, Surprises & Discoveries, Decision Log, and Outcomes & Retrospective as work proceeds. Read `SPEC-T4A.md` and the linked [spec #12](https://github.com/Zero-State-LLC/Noema-Orin/issues/12) and [ticket #13](https://github.com/Zero-State-LLC/Noema-Orin/issues/13) before modifying the implementation. This plan covers only the credential-free T4a slice, **not** live issue #4.

## Purpose / Big Picture

A user can verify that a NOEMA Controller's scripted LOOK goes through the real, pinned first-party client without accessing the hosted world. The official client sees a fake HTTP server on `127.0.0.1`; the server records `ENTER_WORLD`, `OBSERVE`, `LOOK`. The Orin synthetic CLI still runs without the client or network on Python 3.10. Nothing here proves admission to NOEMA or execution on the physical Orin.

## Progress

- [x] (2026-10-31) Confirmed operator-approved runner seam and published spec #12 and ticket #13; left live attach #4 human-gated.
- [x] (2026-10-31) Inspected official client v0.1.23 at `16ec5d1f472295055439975f88567a43fe6ee3b0`; wrote first failing test against the absent optional adapter.
- [x] (2026-10-31) Implemented an opt-in local adapter and observed a 3-command fake-server LOOK sequence. Initial test caught a double `OBSERVE`; removed the redundant call.
- [x] (2026-10-31) Completed fail-closed URL/config/version/rejection coverage. A failing-first discovered external command URI regression found that the client used the published path after enrollment; the adapter now refuses it before a fixture token is issued.
- [x] (2026-10-31) Ran 26 synthetic tests on each of Python 3.10–3.13 and 12 optional tests on each of Python 3.11–3.13 before the last HTTP-guard regression. Installed both wheels into a fresh Python 3.11 venv, imported them from site-packages and ran 13 optional tests outside the checkout after the final fix. The installed synthetic CLI yielded hosted exit 0/ATTEMPTED and offline-spark exit 1/REFUSED with empty stderr.
- [x] (2026-10-31) Re-ran 13 optional tests on Python 3.11–3.13, 26 synthetic tests on Python 3.10–3.13, and 13 optional tests against installed wheels outside the checkout on Python 3.11. Installed CLI hosted and blocked offline receipts retained their exit codes and safe fields.
- [x] (2026-10-31) PR #14 head `6bb2f8d0b7bae4b7d7e3b954d2ef73d451574aa6` passed all ten CI jobs. Independent Spec review passed; Standards blocked on accepting a caller-supplied symlinked config directory and insufficient installed-client import-origin assertion. Replaced caller-supplied config with an owned, private temporary directory; made both import-origin assertions run inside the optional test process and proved that a shadowed client makes the gate fail. The earlier reviews are historical, not clearance for the repaired head.
- [x] (2026-10-31) Re-ran 26 synthetic tests on Python 3.10–3.13, 14 optional tests on Python 3.11–3.13, and 14 installed-package tests on Python 3.11 outside the checkout. A poisoned client-source `PYTHONPATH` fails the installed-origin guard before any optional test runs. Committed the repair as `956b4e173f26b3298c8baf4c222e9b877fc47c5a`.
- [ ] Push the repair, confirm new-head hosted CI and both independent reviews, then merge #13's PR with exact-head guard if authorized.

## Surprises & Discoveries

- `NoemaClient.connect()` enters the fixture world and already observes before returning. An additional `observe()` call produced `ENTER_WORLD, OBSERVE, OBSERVE, LOOK`; a literal sequence assertion caught it.
- The official `HttpGateway.send_command(..., retries=1)` has an internal transport retry, independent of the runner's single `submit` handoff. Never describe the client HTTP-level behavior as guaranteed zero retry. Its loopback-only transport guards every URL and never follows redirects.
- The fixture server resides in pinned `noema-client/tests/fake_server.py`, not in its installable wheel. CI must retain a pinned checkout and add only that checkout's tests directory to test discovery while importing both installed packages outside the workspace.

## Decision Log

- Decision: Keep the optional local proof separate from the CLI and synthetic runner's package floor. Rationale: `noema-client` requires Python >=3.11 while the Python >=3.10 foundation remains useful and dependency-free. Date/Author: 2026-10-31/Bob.
- Decision: Use the official client's pinned fake HTTP server, not a copied protocol server. Rationale: exercises the real public client and reuse of its own fixture while pinning provenance. Date/Author: 2026-10-31/Bob.
- Decision: Admit only explicit `http://127.0.0.1:<ephemeral-port>` with empty config and no NOEMA selectors for the optional adapter. Rationale: prevent a local CI proof from becoming a live endpoint. Date/Author: 2026-10-31/Bob.

## Outcomes & Retrospective

The local implementation has passed the first optional loopback tests on Python 3.11, but the branch and hosted CI are not yet reviewed. After finishing, record exact test counts, a pinned GitHub Actions run, and the remaining #4/#5/#6 blockers here. Do not replace this with a hardware or live-world assertion.

## Context and Orientation

`src/noema_orin/runner.py:run` validates profile, fixture and scripted proposal, then calls `CommandClient.submit` once. `src/noema_orin/ports.py` defines this minimal client interface. `src/noema_orin/receipts.py` constructs an allowlisted synthetic result. `src/noema_orin/__main__.py` is a fake-client-only CLI; it must not import the optional adapter. `src/noema_orin/official_client.py:OfficialLoopbackClient` is the new outer adapter, translating the validated mapping to the official `ActionProposal` and checking `CommandResult.ok`. `tests_optional/test_official_client.py` drives the real pinned client against its own `FakeNoema` server. The only approved test seam is the existing `run(..., client=..., adapter=...)` call; the optional adapter's constructor and `prepare()` are a safety seam for loopback URL and configuration. The canonical Specs SHA is `619d0674518761aa08462d3f5d5966a917259aa1`.

The official client source at `16ec5d1f472295055439975f88567a43fe6ee3b0` defines `NoemaClient(server=None, *, config_home=None, http=None, transport='auto', isolated=False, ...)`, `discover()`, `connect(*, auto_enter=True, ...)`, `act(ActionProposal, *, idempotency_key=None, request_id=None)`, and `close()`. Its `ActionProposal` has `action`, `target_id`, `arguments`, and optional `reason_summary`. The client requires Python >=3.11. `FakeNoema` issues only fixture tokens and binds `127.0.0.1` with `serve_fake`; those are local test traffic, not operator enrollment. A **receipt** is local telemetry, not NOEMA world evidence.

## Plan of Work

First, leave the runner and CLI unchanged. Build `OfficialLoopbackClient` in its own module; reject inherited NOEMA/XDG selectors, nonempty configuration, and anything other than an exact loopback HTTP origin with a port. Use the client's injectable HTTP callable and the standard library `HTTPConnection` to guard every request URL: reject proxies, redirects and discovered command URI substitutions. Call `discover()` then `connect()` in `prepare()`; the latter enters and observes. Only after this may a validated LOOK be converted to `ActionProposal` in `submit`. A false `CommandResult.ok` or a raised client rejection becomes a safe runner `FAILED_SUBMISSION` receipt with no raw exception string. The adapter itself does not emit receipts and is never wired to the CLI.

Second, test one behavioral slice at a time. Run the optional tests against a pinned checkout and verify they fail before the implementation and pass afterward. Add tests for protocol/seal refusal before enrollment, malformed proposals before submission, denied action, returned `ok=False`, lost transport, and non-loopback destination/redirect. Test secret exclusion from model context and receipts. Keep the expected command sequence as a literal independent from the implementation. A bad fixture must still refuse before the optional client at the runner seam.

Third, add a separate GitHub Actions job on Python 3.11–3.13 and ARM Python 3.12. Check out the client at the exact commit, install the client and Orin wheel, change to the runner temporary directory, verify installed import origins and run `tests_optional` with only the pinned client's `tests` directory on `PYTHONPATH`. Preserve the original six-cell foundation matrix. Update the port packet, README and D-005; leave #4–#6 human-gated.

## Concrete Steps

From the Noema-Orin root on branch `integrate/official-client-loopback`, obtain the pinned client into a temporary directory (do not commit it):

    git clone https://github.com/Zero-State-LLC/noema-client.git <temporary-client-checkout>
    git -C <temporary-client-checkout> checkout --detach 16ec5d1f472295055439975f88567a43fe6ee3b0
    git -C <temporary-client-checkout> rev-parse HEAD

In a clean Python >=3.11 environment, install both repositories. From outside either checkout, unset `PYTHONHOME` and all `NOEMA_TOKEN`, `NOEMA_SERVER`, `NOEMA_CONFIG_DIR`, `NOEMA_WORLD_ID`, `NOEMA_ADMIN_TOKEN`, `XDG_CONFIG_HOME`; set `PYTHONPATH` to the **absolute** pinned client's `tests` directory only. Run:

    python -m unittest discover -s <absolute-orin-checkout>/tests_optional -p test_official_client.py -v

The test suite must report the precise count of passing optional tests, see the fake-server command sequence, and issue no request outside loopback. Run the core suite separately from the Orin checkout with `PYTHONPATH=src python -m unittest discover -s tests -q` on each Python 3.10–3.13. From an installed wheel and outside the source checkout, exercise `python -m noema_orin --profile hosted --fixture <absolute-orin-checkout>/fixtures/hosted-look.json --dry-run` and `--profile offline-spark --dry-run`; the first exits 0 with a complete speculative `ATTEMPTED`/`FAKE_HANDOFF` record, the second exits 1 with `REFUSED`/`BLOCKED_SPEC_DEFECT`. Neither command accesses a server. Finally run `git diff --check` before committing.

## Validation and Acceptance

A successful loopback test has only `ENTER_WORLD`, `OBSERVE`, `LOOK` in `FakeNoema.commands`, a single `OfficialLoopbackClient.submissions` count, one fixture-only enrollment, and a complete safe `ATTEMPTED`/`FAKE_HANDOFF` receipt. Denied or returned-unsuccessful actions have `FAILED_SUBMISSION`/`TRANSPORT_FAILURE`, never `ATTEMPTED`; invalid proposals are `REFUSED` before `submit`. Incompatible protocol/seal stops before enrollment or LOOK. The loopback HTTP callable rejects a poisoned discovered URL and never follows redirect or proxy routes. The existing six-cell synthetic CI matrix and installed-CLI receipt assertions still pass unchanged. CI jobs for the optional client use installed packages and Python >=3.11. These outcomes prove local SDK interoperability only. Issues #4–#6 remain open.

## Idempotence and Recovery

The loopback test uses a fresh temporary directory and ephemeral port, cleans up server and config after each case, and can be rerun. An interrupted test can be rerun from the same pinned source SHA; do not reuse or commit fixture-generated credentials. If the client changes version or its public interface, stop and re-pin after a new review. If a protected branch rejects merging, leave a reviewed PR open rather than pushing to `main`. No secret or live endpoint is needed for this plan.

## Artifacts and Notes

Observed initial RED: `ModuleNotFoundError: No module named 'noema_orin.official_client'` from the optional test on Python 3.11. Observed first GREEN after removing the duplicate observe: eight tests passed. A later suite of eleven tests passed before documentation and final verification. These are local code observations, not hosted or physical evidence. The official client source SHA and Specs SHA are distinct; a receipt's `source_sha` remains the Specs pin.

## Interfaces and Dependencies

`OfficialLoopbackClient(server: str, policy: object = None)` creates and owns a private temporary config directory, and implements `prepare() -> None`, `submit(proposal: Mapping[str, object]) -> object`, `model_context() -> dict` and `close() -> None`. Only `submit` is used by the existing `CommandClient` interface. It is an optional local proof, not a general-purpose live client facade. The official client dependency is installed separately only for Python >=3.11 tests, not imported by the synthetic package's `__init__` or CLI. The fake HTTP fixture is loaded from the client source checkout's tests directory, never copied into the Orin wheel.

## Change note

2026-10-31: Initial living plan. The approved T4a scope is loopback only; the real-world gate #4 is intentionally excluded. The discovered double-observe behavior and official transport retry were documented so future operators will not mistake a single runner submission for a single network packet.
