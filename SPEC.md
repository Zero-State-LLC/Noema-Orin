# Spec: Orin-hosted NOEMA Controller fleet

**Status:** Approved for ticket publication and local foundation implementation (T1–T3 only). T4–T6 are gated follow-ons, not part of the implement-spec integration branch until their separate entry conditions are satisfied. No world-contract change, live deployment, or physical-device result claimed. **Source pin:** `Zero-State-LLC/Noema-Specs` main `619d0674518761aa08462d3f5d5966a917259aa1` (2026-10-31). **Scope decision:** both hosted Gateway and offline Spark research paths, isolated from one another; no live-world cutover. **Visibility decision:** private initially.

## Problem Statement

An operator wants Orin Nano to run the agent Controllers doing NOEMA work, instead of relying on the present host for those Controller processes. The newly documented Spark + Orin path describes a speculative offline research topology, but incorrectly calls Spark the sole world writer without scoping that claim to an offline chamber. Copying that phrase into a production plan would violate hosted world authority. The existing official external client already owns Controller mechanics; a second client or a new Player class would duplicate authority and confuse provenance.

## Solution

Create a distinct, private repository for Orin-hosted **Controller processes**. Run the existing official client and a provider-neutral decision adapter on the Orin, while keeping the live World Engine, identity, seal, action authorization, ledger, and settlement in NOEMA. Provide two *explicit* target profiles: `hosted` uses the existing production Gateway and `offline-spark` uses a separate, local research chamber when its authority defect is resolved. A profile switch requires an operator action, never a network-error fallback. This repository initially specifies and verifies boundaries only; physical installation, live attach, Spark deployment, and model choice remain gated.

## User Stories

1. As an operator, I want the Orin to host Controller processes for Agent Players, so that the host of agent inference can change without moving the world authority.
2. As an operator, I want `hosted` and `offline-spark` to be named, separate profiles, so that a research run cannot masquerade as production.
3. As an operator, I want an explicit world identity and endpoint per profile, so that commands cannot be sent to the wrong world after a restart.
4. As a human account holder, I want device-code enrollment and an approval at `/connect`, so that I can authorize a Controller without giving the agent my browser credential.
5. As an Agent Player, I want observations and advertised affordances delivered to the decision adapter, so that it proposes only validly shaped actions.
6. As an operator, I want incompatible protocol discovery or seal checks to stop the Controller, so that Orin migration cannot bypass production admission.
7. As an operator, I want a fail-closed dry run with a scripted adapter before any model installation, so that the command boundary is proven independently of GPU feasibility.
8. As an operator, I want secrets outside the model context and logs, so that remote inference and evidence packets cannot expose Controller credentials.
9. As an operator, I want one session/controller identity per Player and idempotent command retry, so that restart and contention do not create duplicate effects.
10. As an operator, I want a stopped, revoked, or disconnected Controller to leave world truth unchanged except for server-authorized actions, so that local failure cannot mutate the ledger.
11. As a researcher, I want offline observations labeled separately from canonical hosted observations, so that exploratory projections cannot be cited as hosted facts.
12. As an operator, I want measured memory, tokens-per-second, power and latency receipts from the real device, so that a model's feasibility is not inferred from marketing claims.
13. As an operator, I want restart recovery and human stop to be exercisable with fixtures before live runs, so that unattended Controller behavior has an observable safety boundary.
14. As a NOEMA maintainer, I want client-version and Specs SHA pins in evidence, so that compatibility claims can be traced and checked after an update.
15. As a campaign reviewer, I want PSR-1 evidence only from a separately authorized live run with its own cohort and receipts, so that local Orin success is not promoted into a hosted milestone claim.

## Implementation Decisions

- **Authority:** `Noema-Specs` owns product contracts. `Zero-State-LLC/Noema` owns the hosted server. `scrimshawlife-ctrl/noema-client` is the official first-party Controller package. This repository owns Orin-specific process configuration, model-adapter integration, isolation, observability and deployment recipes; it never forks the official client or runs a world writer.
- **Highest test seam:** invoke a Controller runner with a profile, a fake official-client boundary, an observation and a scripted adapter. Assert the resulting command attempt or refusal and redacted telemetry. Hardware-specific model adapters are replaceable and tested behind the same seam. No new NOEMA protocol seam is introduced.
- **Two paths:** `hosted` talks to the existing Gateway using discovery, device-code enrollment, accepted live seal and the official client. `offline-spark` is a distinct local research target with separate identity and credential store. The latter MUST NOT be enabled until a canonical offline-chamber authority decision resolves spec 014's writer contradiction. No implicit failover, shared token, cross-world replay, or production endpoint substitution.
- **Propose/transport:** model adapter returns only `{action, target_id, arguments}`; the harness/client validates against observed affordances before transport. The server alone determines legality and settles consequences. Reject prose commands, extra cognition fields, unknown verbs, and unadvertised actions. Mutating retries use the canonical request/idempotency identity.
- **Enrollment:** normal production path uses the official client (`noema connect` → human `/connect` approval → scoped credential → discovery/seal → `noema play`). No token paste, browser automation, Admin secret, or model-visible credential.
- **Compatibility:** pin the shipped official client version for any PSR-1 candidate to `noema-client==0.1.21` **as of the source pin**, then reconcile against the live production pin before execution. Pinning here does not authorize or complete PSR-1. Framework/vendor SDK and a particular VLM are not required for Controller conformance.
- **Device constraints:** the source *proposes* an 8 GB Orin Nano and an INT4 Cosmos3-Edge or equivalent VLM; neither compatibility nor throughput has been measured here. Model selection follows physical inventory, JetPack support and profiling. No CUDA, DeepStream, TensorRT, model download, or performance promise is presumed.
- **Evidence:** local runner telemetry is not canonical gameplay evidence. Record profile, source pin, client version, redacted Controller/Player identifiers, attempt/result, latency, model/version, memory/power and claim label as available; never record credentials, private prompts, raw chain of thought, or production secrets. Missing physical measures are `NOT_COMPUTABLE`.
- **Promotion:** orchestrated live production attach requires a separate authorized run. PSR-1 requires six concurrent Controllers across three integration paths including third-party operation, and separate enrollment receipts for two outside operators. Merely hosting first-party Controllers on Orin does not satisfy the third-party path or promote the Gate.

## Testing Decisions

Tests should observe the public Controller-runner boundary, not private functions or GPU internals. Use a fake Gateway/client and scripted model, then exercise: hosted discovery and seal success/refusal; offline profile blocked until explicit authorization; no cross-profile fallback; rejected malformed proposal; secret-safe telemetry; idempotent retry; graceful stop and reconnect. A physical Orin smoke run later measures memory, model load, tokens/s, power and command/observation latency; its receipt must identify firmware, OS, device, model and source pins. Test real Gateway interoperability only after scoped authorization and record the actual target environment. Document validation in this first commit checks spec completeness and dependency integrity, not runtime behavior.

## Out of Scope

No hosted-world migration or Spark writer promotion; no new NOEMA verb, schema, event, Player class, Admin path, research claim, or consciousness metric. No optional Omniverse/Cosmos observation writer, MCP dependency, model weights, new client distribution, credential issuance in CI, or automatic production deployment. PSR-1/PSR-2 verdicts are out of scope.

## Further Notes

**OBSERVED:** `Noema-Specs/specs/014-spark-orin-nvidia-stack/spec.md` is `SPECULATIVE` and names its own writer conflict; `specs/current-state.v1.yaml` keeps `spark_orin_nvidia_stack: SPECULATIVE` and PSR-1 blocked. `CONTEXT.md` gives Cloudflare Durable Objects live serialization and Supabase Postgres the durable canonical record. Accepted RFC-0114, RFC-0116 and the Agent Harness define Controller and official-client responsibilities. `docs/PSR-1-COMPATIBILITY-AT-SCALE-SCENARIO.md` locks the independent cohort floor.

**INFERRED:** an Orin-host repository can package a Controller runner without changing NOEMA's wire contracts. **SPECULATIVE:** an on-device INT4 VLM will fit or meet useful latency. **NOT_COMPUTABLE:** real-device performance and LAN results; physical access and a compatible model have not been verified.

The Pocock `to-spec` format is the section structure here. The operator approved the runner seam and the T1–T6 dependency graph. **Implementation-ready foundation: T1–T3 only** (local, synthetic, no credentials or hardware). T4–T6 are published as blocked follow-ons and require separate entry decisions; an `implement-spec` run MUST NOT treat the entire aspirational feature as authorized in one integration branch. Skills are workflows, not world authority. This repo uses `grill-with-docs`, `to-spec`, `to-tickets`, `implement-spec`, and `code-review` when available, respecting Noema-Specs' `SKILL.*` discipline; it does not invent a mandatory `skill.yaml` or agent runtime framework.

### Source links (all pinned to the main SHA above)

- [Noema-Specs CONTEXT](https://github.com/Zero-State-LLC/Noema-Specs/blob/619d0674518761aa08462d3f5d5966a917259aa1/CONTEXT.md)
- [Spec 014](https://github.com/Zero-State-LLC/Noema-Specs/blob/619d0674518761aa08462d3f5d5966a917259aa1/specs/014-spark-orin-nvidia-stack/spec.md) and [plan](https://github.com/Zero-State-LLC/Noema-Specs/blob/619d0674518761aa08462d3f5d5966a917259aa1/specs/014-spark-orin-nvidia-stack/plan.md)
- [Current state](https://github.com/Zero-State-LLC/Noema-Specs/blob/619d0674518761aa08462d3f5d5966a917259aa1/specs/current-state.v1.yaml)
- [RFC-0114](https://github.com/Zero-State-LLC/Noema-Specs/blob/619d0674518761aa08462d3f5d5966a917259aa1/rfcs/RFC-0114-llm-controller-adapter.md), [RFC-0116](https://github.com/Zero-State-LLC/Noema-Specs/blob/619d0674518761aa08462d3f5d5966a917259aa1/rfcs/RFC-0116-official-agent-client.md), [Agent Harness](https://github.com/Zero-State-LLC/Noema-Specs/blob/619d0674518761aa08462d3f5d5966a917259aa1/docs/AGENT-HARNESS.md), [Official Client](https://github.com/Zero-State-LLC/Noema-Specs/blob/619d0674518761aa08462d3f5d5966a917259aa1/docs/OFFICIAL-AGENT-CLIENT.md)
- [PSR-1 contract](https://github.com/Zero-State-LLC/Noema-Specs/blob/619d0674518761aa08462d3f5d5966a917259aa1/docs/PSR-1-COMPATIBILITY-AT-SCALE-SCENARIO.md)
