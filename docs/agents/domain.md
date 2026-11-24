# Domain docs for Pocock engineering skills

**Layout:** single-context. Read this repository's `SPEC.md`, `DECISIONS.md`, and `AGENTS.md` before proposing changes. NOEMA vocabulary and authority come from the pinned `Noema-Specs` source links in `SPEC.md`, not from this repository.

## Issue tracker

GitHub Issues on `Zero-State-LLC/Noema-Orin` (public). Read the full issue and comments before editing. Use one independently demoable vertical slice per issue and list `Blocked by` issue links. No issue marked `ready-for-agent` is authorization to run against production.

## Triage labels

Canonical Pocock defaults when created: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. Apply `ready-for-agent` only after the operator approves the proposed seam and ticket dependency graph. Hardware and canon-authority gates remain `ready-for-human` or blocked, not implicit implementation work.

## Domain vocabulary

An **Agent** inhabits as a **Player** through an external **Controller**. An Orin-hosted process is a Controller, never a Player class or a world writer. `hosted` and `offline-spark` must remain separately scoped profiles. Read the local [GLOSSARY](../../GLOSSARY.md) for target profile, fixture observation, submission attempt, pre-submission refusal, failed submission attempt, and dry-run receipt. The pinned `Noema-Specs/GLOSSARY.md` owns canonical identity terms; `CONTEXT.md` in Noema-Specs owns authority. Neither this repository's glossary nor its [synthetic output-boundary ADR](../adr/0001-synthetic-runner-output-boundary.md) overrides accepted Noema-Specs RFCs.

## Test seam

Prefer one high-level runner seam: validate profile before fixture before adapter before fake client. A pre-submission refusal invokes no client; a failed fake-client handoff is **one attempted submission**, not zero. Exactly one allowlisted JSON outcome on stdout per invocation; errors exit nonzero without echoing raw inputs/exceptions on either stream. No retries or cross-profile fallback. A synthetic `ATTEMPTED` handoff never means world acceptance or device readiness.

---

# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`GLOSSARY.md`** at the repo root, or
- **`GLOSSARY-MAP.md`** at the repo root if it exists: it points at one `GLOSSARY.md` per context. Read each one relevant to the topic.
- **`docs/adr/`**: read ADRs that touch the area you're about to work in. In multi-context repos, also check `src/<context>/docs/adr/` for context-scoped decisions.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

## File structure

Single-context repo (most repos):

```
/
├── GLOSSARY.md
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md
└── src/
```

Multi-context repo (presence of `GLOSSARY-MAP.md` at the root):

```
/
├── GLOSSARY-MAP.md
├── docs/adr/                          ← system-wide decisions
└── src/
    ├── ordering/
    │   ├── GLOSSARY.md
    │   └── docs/adr/                  ← context-specific decisions
    └── billing/
        ├── GLOSSARY.md
        └── docs/adr/
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `GLOSSARY.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (event-sourced orders), but worth reopening because…_
