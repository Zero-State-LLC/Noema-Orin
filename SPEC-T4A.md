## Problem Statement

The Orin-hosted Controller foundation demonstrates a scripted LOOK with a synthetic `CommandClient.submit` fake. The official first-party client instead exposes `NoemaClient.act(ActionProposal)`. Without a credential-free proof of that translation, a clean synthetic run says nothing about whether the Controller can use the real public client on the eventual Orin. Issue #4 still requires separate authorization for isolated-world attach; production and hardware are not available as test substitutes.

## Solution

Add a small optional official-client adapter at the existing Controller runner seam. On Python 3.11 or newer, prove a scripted hosted LOOK through the pinned, real `noema-client` v0.1.23 against its own loopback `FakeNoema` HTTP server, with temporary configuration, no operator credentials and no external endpoint. Keep the synthetic CLI and its exact receipt contract unchanged on Python 3.10–3.13. This slice is T4a, not closure of #4.

## User Stories

1. As an operator, I want a real first-party client behind the already-tested runner seam, so that the Orin package does not fork Controller mechanics.
2. As an operator, I want a local loopback proof, so that I can verify client interoperability without granting a live-world attach.
3. As an operator, I want an explicit Python compatibility gate, so that the 3.10 synthetic installer remains usable while the client requiring 3.11+ is optional.
4. As a Controller maintainer, I want invalid proposal shapes refused before client handoff, so that malformed adapter output cannot become an official action.
5. As a Controller maintainer, I want client policy refusal and unsuccessful client results distinguished from successful fake handoffs, so that a denial never appears as `ATTEMPTED`.
6. As an operator, I want the real client's discovery and seal checks exercised against the fake server, so that an incompatible seal or discovery result stops before LOOK.
7. As an operator, I want all network traffic limited to loopback and credentials excluded from the model and receipts, so that CI cannot silently become a production probe.
8. As a reviewer, I want a recorded client commit, version, public methods and observed local command sequence, so that the proof is reproducible and cannot be mistaken for world acceptance.
9. As a future device operator, I want the unresolved live, hardware and offline Spark gates stated in the port packet, so that local green tests do not imply Orin readiness.

## Implementation Decisions

- Reuse the high-level `run(profile, fixture, client, adapter)` seam and the existing `CommandClient.submit` interface. A thin optional adapter converts the already validated `{action, target_id, arguments}` proposal to the public `ActionProposal`, then delegates to the real `NoemaClient.act`. Do not modify the runner's validation or synthetic CLI.
- Pin the official source to `16ec5d1f472295055439975f88567a43fe6ee3b0` (v0.1.23); the canonical Specs SHA is `619d0674518761aa08462d3f5d5966a917259aa1`. This optional client requires Python >=3.11 while the stdlib-only synthetic package retains >=3.10. Do not import the optional adapter at package startup.
- `NoemaClient` public methods at this pin are `discover() -> Discovery`, `connect(..., auto_enter=True) -> StoredCredential`, `act(proposal: ActionProposal, *, idempotency_key=None, request_id=None) -> CommandResult`, and `close()`. `ActionProposal` has `action`, `target_id`, `arguments`, `reason_summary`. An unsuccessful `CommandResult.ok` or raised rejection is a failed handoff, never a successful fake attempt.
- Use the official client's own `FakeNoema` fixture on `127.0.0.1` with ephemeral port, temporary `config_home`, explicit `server` and HTTP transport. `connect()` may perform fixture-only device enrollment and send `ENTER_WORLD`, `OBSERVE` before LOOK. These commands are fake-server traffic, not human or production enrollment. The runner submits once; the fake server sees the complete setup sequence.
- Require a known loopback URL when creating any helper for the local proof; no silent default server, production route, `isolated=True`, Admin token, production credential, or real-world connection in tests or CI. Scrub NOEMA and XDG configuration selectors. The test harness may read fixture-generated tokens internally, but never forward them into the scripted decision adapter or receipts.
- Keep the CLI's `FAKE_HANDOFF`, `transport=fake`, `client_version=UNVERIFIED`, `claim_label=SPECULATIVE` and `device_metrics=NOT_COMPUTABLE` records untouched. The optional proof has separate test observations and must never claim official world acceptance.

## Testing Decisions

- Test observable behavior primarily at the existing runner seam with the real official client and pinned loopback fake server. A thin adapter seam is only tested where translating the public client result cannot be observed cleanly through runner receipts; avoid mocking internals of `NoemaClient`.
- Begin with one failing test for a validated hosted LOOK through the real client and exact fake-server command sequence, then implement minimally. Add narrow failing-first slices for invalid proposal refusal, seal/discovery rejection, a denied client policy, an `ok=False` command result, secret exclusion, and a non-loopback guard. Assert exact submission counts and safe receipts where applicable.
- Follow the established synthetic tests for profile/fixture/proposal refusal and complete allowlisted receipts. Existing Python 3.10–3.13 tests and installed CLI matrix must remain green. Run optional-client tests only on Python >=3.11 with the pinned client installed in a clean environment. Production network is forbidden in CI.

## Out of Scope

No real isolated-world attach, production enrollment, live Gateway traffic, actual Orin run, model selection, GPU/JetPack claim, offline Spark writer, PSR-1 gate, new Player class, official-client fork, or receipt schema change. This spec does not close #4, #5, or #6.

## Further Notes

**OBSERVED:** The canonical Specs pin still matches main; official client main still matches the inspected v0.1.23 commit. The client fixture provides `FakeNoema` and `serve_fake`, binding a loopback HTTP server. `NoemaClient.act` validates and sends a command; `CommandResult.ok` may be false without an exception. The existing Orin runner validates before `submit`. **INFERRED:** a minimal adapter can bridge these public interfaces without changing synthetic semantics. **NOT COMPUTABLE:** real device or isolated-world acceptance. Governing contracts: `SPEC-FOUNDATION.md`, `DECISIONS.md`, `docs/adr/0001-synthetic-runner-output-boundary.md`, and `docs/ORIN-8GB-PORT.md` at Noema-Orin main `6d83852fc1bd040f1525de5ac5f0edb510d92d3c`. The operator approved this seam and split on 2026-10-31; issue #4 retains its human gate.
