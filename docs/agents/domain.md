# Domain docs for Pocock engineering skills

**Layout:** single-context. Read this repository's `SPEC.md`, `DECISIONS.md`, and `AGENTS.md` before proposing changes. NOEMA vocabulary and authority come from the pinned `Noema-Specs` source links in `SPEC.md`, not from this repository.

## Issue tracker

GitHub Issues on `Zero-State-LLC/Noema-Orin` (private). Read the full issue and comments before editing. Use one independently demoable vertical slice per issue and list `Blocked by` issue links. No issue marked `ready-for-agent` is authorization to run against production.

## Triage labels

Canonical Pocock defaults when created: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. Apply `ready-for-agent` only after the operator approves the proposed seam and ticket dependency graph. Hardware and canon-authority gates remain `ready-for-human` or blocked, not implicit implementation work.

## Domain vocabulary

An **Agent** inhabits as a **Player** through an external **Controller**. An Orin-hosted process is a Controller, never a Player class or a world writer. `hosted` and `offline-spark` must remain separately scoped profiles. `CONTEXT.md` in Noema-Specs is authority and is not replaceable by this file. This repository has no local RFC or ADR that can override accepted Noema-Specs RFCs.

## Test seam

Prefer one high-level runner seam: profile + fake official-client/Gateway + observation + scripted decision adapter → command attempt or refusal plus redacted telemetry. Do not create provider-specific acceptance semantics or claim that a host-only fake proves device readiness.
