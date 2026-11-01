# Spec: NOEMA Orin Controller foundation (T1–T3 only)

**Status:** Approved for local synthetic implementation. This is the **sole input specification for the first Pocock `implement-spec` integration branch**. Parent roadmap: [SPEC.md](SPEC.md). Tracker: [foundation issue #7](https://github.com/Zero-State-LLC/Noema-Orin/issues/7), tickets [#1](https://github.com/Zero-State-LLC/Noema-Orin/issues/1), [#2](https://github.com/Zero-State-LLC/Noema-Orin/issues/2), [#3](https://github.com/Zero-State-LLC/Noema-Orin/issues/3). **Do not include #4–#6 in this branch.** Authority pin: `Noema-Specs` main `619d0674518761aa08462d3f5d5966a917259aa1`; implementation guidance: [foundation ExecPlan](execplan/01-foundation.md).

## Problem Statement

An operator wants to move NOEMA Agent Player Controller processes onto an Orin Nano, but there is no independently verifiable local Controller-host boundary yet. The speculative Spark topology conflicts with hosted world-writer authority if treated as a live migration. Starting with hardware installation or live enrollment would entangle unproven device behavior, secrets, and canonical NOEMA operations.

## Solution

Build a deterministic, **no-network dry-run** Controller runner. The operator chooses an explicit `hosted` target, supplies a non-secret fixture, and receives one attempted LOOK plus a redacted, provenance-bound telemetry receipt. The `offline-spark` target is recognized but refuses before invoking an adapter or client; a failed hosted target never falls back to it. This first release is a synthetic foundation, not a live Controller, official-client integration, hardware measurement or world cutover.

## User Stories

1. As an operator, I want to select `hosted` explicitly, so that no default target is silently chosen.
2. As an operator, I want a repeatable dry-run CLI, so that I can inspect one proposed command without access to a NOEMA account.
3. As an Agent Player's operator, I want a scripted adapter to propose a LOOK from a fixture observation, so that the decision seam can be tested without a model.
4. As an operator, I want a fake client to record the attempted command, so that no network or real world mutation occurs.
5. As an operator, I want `offline-spark` to refuse while its source spec is defective, so that research execution cannot be mistaken for the hosted world.
6. As an operator, I want invalid or missing profiles to fail before any command attempt, so that errors cannot choose a different world.
7. As an operator, I want transport failure to stop rather than trigger cross-profile fallback, so that the target remains pinned.
8. As an operator, I want a source-pinned, claim-labeled receipt, so that a fixture result is never promoted into real-world evidence.
9. As an operator, I want secrets and private cognition absent from the receipt and CLI output, so that synthetic inputs cannot leak into reports.
10. As a reviewer, I want tests that fail before each behavior is implemented and pass afterward, so that the foundation is demonstrable rather than a prose-only promise.

## Implementation Decisions

- The sole high-level seam is a Controller runner with an explicit profile, non-secret fixture observation, scripted decision adapter and fake client; its outputs are a command attempt or a typed refusal and redacted receipt.
- Model output is confined to `{action, target_id, arguments}`. A fake client does not authorize world actions; it records only an attempt. The World Engine remains authoritative, outside this repository.
- `hosted` is a label for a dry-run target, **not** a stored production endpoint or credential. `offline-spark` returns `BLOCKED_SPEC_DEFECT` before adapter/client invocation. Missing/unknown profile and fake transport failures never fall back.
- A receipt distinguishes `ATTEMPTED` from accepted/settled. Record source pin, profile, fake transport, action/result, `claim_label=SPECULATIVE`, `client_version=UNVERIFIED`, and `device_metrics=NOT_COMPUTABLE`. Do not persist arbitrary fixture contents, tokens, prompts, authorization headers, browser credentials or model reasoning.
- Reuse the existing official first-party Controller package in a **future** separately gated integration; do not copy its code or invent a new Player class. Do not add NOEMA protocol fields or a `skill.yaml`.

## Testing Decisions

Test at the runner and CLI behavior seam, not at private parsing helpers. The `hosted` fake-client scenario records exactly one LOOK attempt and returns a single machine-readable receipt; the `offline-spark`, unknown/missing profile and transport-failure scenarios have no cross-target call. Inject distinct sentinel secrets into fake inputs and assert serialized output excludes all of them. Each ticket supplies a failing test before implementation and then a passing one; run the full local suite and `git diff --check`. These tests prove only synthetic orchestration and document invariants; no hardware or hosted-world claim is permitted. Exact planned paths, test commands, expected behavior and recovery guidance live in the [ExecPlan](execplan/01-foundation.md).

## Out of Scope

Issues #4–#6: official-client/API integration, isolated-world or live enrollment, physical Orin measurements, model selection or deployment, offline Spark execution and canonical spec-014 resolution. Also excluded: hosted world cutover, production commands, new verbs/events/schemas, admin access, PSR-1 promotion, consciousness claims and real credentials. The first implementation is complete without any of these. They require separate decisions after this integration branch is reviewed.

## Further Notes

**OBSERVED:** Noema-Specs `CONTEXT.md` assigns hosted live serialization to Cloudflare Durable Objects and durable world records to Supabase Postgres; its spec 014 is SPECULATIVE and flags the Spark-writer conflict. RFC-0114 specifies a constrained model proposal and RFC-0116 identifies `scrimshawlife-ctrl/noema-client` as the official client. **INFERRED:** an Orin-ready Controller host can use a fake-client runner as its first seam. **SPECULATIVE:** a chosen VLM fits or performs on Orin. **NOT_COMPUTABLE:** device throughput, memory, power, latency, and live compatibility until independently measured.

The operator approved the runner seam and ticket graph. This document is the foundation-only `to-spec` output for `implement-spec`; #7 is its parent issue, with #1–#3 as implementation tickets and explicit blocking edges. The broader [SPEC.md](SPEC.md) is an umbrella roadmap. #4–#6 are gated follow-ons, not part of this implementation. The Pocock `implement-spec` procedure may now start with #1, then #2 and #3 on fresh worktrees, merge to one foundation integration branch, and finish with code review; it must not treat a `ready-for-human` issue as a runnable ticket.
