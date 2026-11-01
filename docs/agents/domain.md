# Domain docs for Pocock engineering skills

**Layout:** single-context. Read this repository's `SPEC.md`, `DECISIONS.md`, and `AGENTS.md` before proposing changes. NOEMA vocabulary and authority come from the pinned `Noema-Specs` source links in `SPEC.md`, not from this repository.

## Issue tracker

GitHub Issues on `Zero-State-LLC/Noema-Orin` (private). Read the full issue and comments before editing. Use one independently demoable vertical slice per issue and list `Blocked by` issue links. No issue marked `ready-for-agent` is authorization to run against production.

## Triage labels

Canonical Pocock defaults when created: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. Apply `ready-for-agent` only after the operator approves the proposed seam and ticket dependency graph. Hardware and canon-authority gates remain `ready-for-human` or blocked, not implicit implementation work.

## Domain vocabulary

An **Agent** inhabits as a **Player** through an external **Controller**. An Orin-hosted process is a Controller, never a Player class or a world writer. `hosted` and `offline-spark` must remain separately scoped profiles. Read the local [GLOSSARY](../../GLOSSARY.md) for target profile, fixture observation, submission attempt, pre-submission refusal, failed submission attempt, and dry-run receipt. The pinned `Noema-Specs/GLOSSARY.md` owns canonical identity terms; `CONTEXT.md` in Noema-Specs owns authority. Neither this repository's glossary nor its [synthetic output-boundary ADR](../adr/0001-synthetic-runner-output-boundary.md) overrides accepted Noema-Specs RFCs.

## Test seam

Prefer one high-level runner seam: validate profile before fixture before adapter before fake client. A pre-submission refusal invokes no client; a failed fake-client handoff is **one attempted submission**, not zero. Exactly one allowlisted JSON outcome on stdout per invocation; errors exit nonzero without echoing raw inputs/exceptions on either stream. No retries or cross-profile fallback. A synthetic `ATTEMPTED` handoff never means world acceptance or device readiness.
