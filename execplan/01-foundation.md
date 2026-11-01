# Build an Orin-hosted Controller runner without moving NOEMA world authority

This ExecPlan is a living document. Keep Progress, Surprises & Discoveries, Decision Log, and Outcomes & Retrospective current. The first release is an **offline, fake-client demonstration** of a hosted-profile Controller and a refused offline-Spark profile. It does not attach to the live world or run on an Orin. The operator can execute `python3 -m unittest discover -s tests -v`, then `PYTHONPATH=src python3 -m noema_orin --profile hosted --fixture fixtures/hosted-look.json --dry-run` and see one validated LOOK attempt and a redacted receipt. Until separately authorized and tested, real transport and GPU inference remain unavailable.

## Purpose / Big Picture

Move the *Controller host*, not the world writer. A Controller running on Orin can eventually propose actions for an Agent Player to the NOEMA Gateway, while Cloudflare Durable Objects keep live serialization and Postgres the canonical record. This plan proves the Controller boundary without needing hardware, secrets, a model, or a production account. The offline Spark path is structurally separate and refuses execution until Noema-Specs resolves spec 014's authority defect.

## Progress

- [x] (2026-10-31) Pin governing Noema-Specs and identify spec 014's open defect.
- [x] (2026-10-31) Confirm two separate paths, no cutover, and private repo with operator.
- [x] (2026-10-31) Operator approved the proposed runner test seam and T1–T6 dependency graph for publication.
- [ ] Publish T1–T6 tickets in the private tracker with exact blocking edges; only T1–T3 are ready-for-agent.
- [ ] T1: deliver deterministic hosted dry-run with a scripted proposal and fake client.
- [ ] T2: deliver isolation/refusal for offline Spark, invalid profiles, and cross-target fallback.
- [ ] T3: deliver secret-safe, labeled dry-run receipts with source/client pins.
- [ ] T4: integrate the existing official client behind the tested boundary in an isolated test environment; live attach requires a separate explicit authorization.
- [ ] T5: collect physical Orin feasibility receipts before selecting a model or changing the operational posture.
- [ ] T6: resolve the offline Spark writer defect *in Noema-Specs* before enabling that separate research path.

## Surprises & Discoveries

- Spec 014 calls Spark the sole writer, while `Noema-Specs/CONTEXT.md` gives hosted live serialization to Cloudflare Durable Objects and durable canonical history to Postgres. The source flags this as a SPEC DEFECT. This repo cannot resolve it by reinterpretation.
- The official Python Controller already has its own repository (`scrimshawlife-ctrl/noema-client`). Orin integration must not copy its internals or create a competing package.

## Decision Log

- Decision: make the first implementation local and fake-client-only, with real transport a later ticket. Rationale: hardware and live admission are unproven; deterministic behavior at the runner seam is independently demonstrable. Date/Author: 2026-10-31/Bob.
- Decision: `offline-spark` is a profile that refuses to run, not a partially working world-writer. Rationale: fail closed on a canonical defect and make cross-profile mistakes testable. Date/Author: 2026-10-31/Bob.
- Decision: hosted and offline work never share credentials, endpoint discovery state, or receipt namespaces. Rationale: a fake or research result cannot become a production claim. Date/Author: 2026-10-31/Bob.

## Outcomes & Retrospective

Specification and ticket graph drafted. No runner, real-client integration, hardware measurement, or live attach has been implemented. Update this section with exact commands/results at each milestone.

## Context and Orientation

`SPEC.md` is the Pocock `to-spec` document; `DECISIONS.md` lists unresolved authority and hardware gates. `AGENTS.md` constrains all contributors. The authoritative source is `Zero-State-LLC/Noema-Specs` main SHA `619d0674518761aa08462d3f5d5966a917259aa1`. Its `CONTEXT.md` establishes world authority; spec 014 is speculative; accepted RFC-0114 defines the model's proposal boundary and RFC-0116 names the separate official client. The source PSR-1 scenario requires six concurrent Controllers across three integration paths and retained outside-operator enrollment receipts. This plan neither supplies those receipts nor authorizes the campaign.

A **Controller** is external software acting for an Agent Player. A **profile** is local target configuration, not a new protocol. A **scripted adapter** is a deterministic replacement for a model in tests. A **fake client** accepts or rejects attempted commands without network access. **Dry-run** means no network, no credential loading, and no canonical world mutation. **Seal** means the published live prompt hash admitted by the Gateway, not a permission granted by this repository. A **receipt** is local telemetry, not canonical evidence.

## Plan of Work and proposed tracer-bullet tickets

Each ticket below fits one fresh context window, delivers one behavior through the highest runner seam, and has explicit blocking edges. The operator approved this graph for publication. **The first `implement-spec` run is scoped to T1–T3 only**: those are the complete local foundation and can be independently verified without hardware or credentials. Publish T4–T6 as gated follow-ons, not ready-for-agent; their entry conditions require separate review before a later implementation cycle. `implement-spec` uses the committed spec and approved tracker tickets on one integration branch with a fresh implementer worktree per frontier ticket, tests first, and code review. Do not silently include hardware, canon changes, or live deployment in the first integration branch.

**T1, Hosted dry-run (no blockers).** Create `pyproject.toml` for a Python >=3.11 package, `src/noema_orin/{__init__,__main__,runner,ports}.py`, `fixtures/hosted-look.json`, and `tests/test_runner.py`. One CLI invocation with `--profile hosted --fixture ... --dry-run` loads a public, non-secret fixture, prepares a deterministic LOOK proposal `{ "action": "LOOK", "target_id": null, "arguments": {} }`, sends it to a fake client, and emits a receipt with `status=ATTEMPTED`, `profile=hosted` and `transport=fake`. Keep the runner independent of model SDKs and official-client implementation details. Start by writing an integration test that imports and calls `noema_orin.runner.run(profile="hosted", fixture=..., client=FakeClient(), adapter=ScriptedAdapter())`; run it RED with `PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_runner.py' -v` (initial import/attribute failure), implement minimally, then rerun GREEN. Use `python3 -m noema_orin --profile hosted --fixture fixtures/hosted-look.json --dry-run` with `PYTHONPATH=src` to observe a single JSON receipt. It must never call the network. This is the top-level seam that all later tickets reuse.

**T2, Fail-closed target isolation (blocked by T1).** Add `src/noema_orin/profiles.py`, `tests/test_profiles.py`, and static fixture `fixtures/offline-spark-look.json`. Explicit `hosted` selects a fake Gateway target; `offline-spark` returns `BLOCKED_SPEC_DEFECT` *before* model or client invocation, even when the hosted fake succeeds. Unknown or absent profiles return a nonzero CLI exit and no command attempt. Tests first assert these observable outcomes, RED when the profile layer is absent, GREEN after implementation. Simulate a network failure and assert that it does not switch targets. No real Spark endpoint or credentials are added.

**T3, Redacted evidence (blocked by T1; may run parallel with T2).** Add `src/noema_orin/receipts.py`, `tests/test_receipts.py`, and `docs/evidence/README.md`. A dry-run receipt records only source SHA, profile, `client_version` marked `UNVERIFIED` unless probed, action/result, `claim_label=SPECULATIVE` for a fixture, and `device_metrics=NOT_COMPUTABLE`; no token, prompt, browser credential, raw authorization header or private cognition. A test inserts sentinel secret values into fake inputs and asserts those strings are absent from serialized receipts and CLI output. Write RED before code, then GREEN. Keep IDs redacted/hash-only and no automatic upload.

**T4, Existing-client integration (blocked by T1, T2, T3; separate authority check).** Once the operator approves local-only integration and the official client API has been inspected at its pinned version, add `src/noema_orin/official_client.py` and `tests/test_official_client.py`. Do not guess an API from the Specs prose: first record the installed `noema-client` version and exact public methods. Adapter tests use a fake client and prove discovery/seal refusal and no token in model context. An isolated-world integration test may run only with explicit, safe credentials and endpoint authorization. Never run against production as part of CI or this ticket. If a stable public API is missing, stop and open a client-repo issue rather than copying private internals.

**T5, Real-device feasibility (blocked by T1–T3 and access to device).** Add an opt-in measurement script and a receipt template only after inventorying the exact Orin board, OS/JetPack, storage, memory and power. Measure actual model load, peak memory, tokens/s and command-to-observation latency, with versions and run identifiers. Zero fake measurements count as physical acceptance. Any model choice, especially Cosmos3-Edge INT4, is conditional on license, deployment compatibility and measured 8 GB fit; `NOT_COMPUTABLE` until then.

**T6, Offline Spark execution (blocked by a Noema-Specs canonical decision resolving G-001, and by T2–T4).** Record the exact accepted authority and isolated chamber contract first. Only then enable a separate offline endpoint/credential store and test that its world identity and receipts cannot cross into hosted. If authority remains unresolved, leave T6 blocked indefinitely. No ticket here may edit canonical Noema-Specs or promote its speculative spec.

## Concrete Steps

From the root of this repository, first verify `git status --short --branch` is clean and read `SPEC.md`, `DECISIONS.md`, `AGENTS.md` and the linked Noema-Specs authority. For each authorized ticket, create the test before the implementation, run the targeted test expecting a meaningful RED, implement only that slice, run it GREEN, then run `PYTHONPATH=src python3 -m unittest discover -s tests -v` and `git diff --check`. After T1, run `PYTHONPATH=src python3 -m noema_orin --profile hosted --fixture fixtures/hosted-look.json --dry-run`; a single JSON result must report `ATTEMPTED`, `hosted`, `fake`, and must not contain a credential. After T2, `PYTHONPATH=src python3 -m noema_orin --profile offline-spark --fixture fixtures/offline-spark-look.json --dry-run` must exit nonzero with `BLOCKED_SPEC_DEFECT` and no command sent. Unknown/missing profile must also fail without reaching the client.

Run tests under Python >=3.11. `PYTHONPATH=src` is set explicitly in every independent example to avoid importing a different checkout. No Docker, SDK, GPU or network is required for T1–T3. If a source package is installed editable instead, preserve the same test seam. Use explicit `git add` paths, Conventional Commit messages, and one integration branch; do not use `git add -A`.

## Validation and Acceptance

T1–T3 are complete only if the exact unit/integration commands return zero, the CLI behaves as stated, the blocked profile makes zero fake-client calls, and a sentinel secret is absent from outputs. These are **synthetic** results. T4 requires an independently verified official-client public API and authorized isolated-world result; local tests cannot prove production admission. T5 requires real Orin measurements tied to device and software pins. T6 requires an accepted Noema-Specs authority decision and separate research-world verification. PSR-1 remains blocked until its own external enrollment and promotion criteria are met; no milestone here closes it.

## Idempotence and Recovery

Dry-run never writes world state or contacts a real endpoint, so it can be repeated. Repeated receipt generation may use a fresh local run ID but must not overwrite prior receipts. Never persist a token in a fixture or failure log. On missing authority, hardware, client API or enrollment, stop the affected ticket while retaining completed local slices; do not silently choose a fallback target. If the official-client API differs from the plan, amend this living plan with observed signatures and rerun its affected tests before implementation.

## Artifacts and Notes

Source boundaries: `Noema-Specs/CONTEXT.md` (Platform authority), `specs/014-spark-orin-nvidia-stack/spec.md` (speculative, writer defect), `rfcs/RFC-0114-llm-controller-adapter.md` (proposal), `rfcs/RFC-0116-official-agent-client.md` (distribution), `docs/PSR-1-COMPATIBILITY-AT-SCALE-SCENARIO.md` (blocked gate). All are pinned at `619d0674518761aa08462d3f5d5966a917259aa1` in `SPEC.md`.

## Interfaces and Dependencies

Expose `run(profile: str, fixture: Mapping[str, object], client: CommandClient, adapter: DecisionAdapter) -> Receipt`. `DecisionAdapter.decide(observation) -> ActionProposal` returns only `action`, `target_id`, and `arguments`; `CommandClient.submit(proposal) -> result` is implemented by a fake first and by a thin wrapper of the existing official client only after its API is verified. The CLI selects a profile, loads fixture data and serializes a receipt. Domain types and the runner have **no dependency** on the official-client SDK, NVIDIA tooling, filesystems or networking; adapters at the outer boundary own those. Schema and full signature details may be refined from a first failing test, but never weaken the observable refusal or secret-exclusion criteria.

## Change note

2026-10-31: Initial self-contained implementation plan. Local dry-run and offline refusal are executable first; hardware, live attach and Spark execution are explicit gates, not implicit phases of a single deployment.
