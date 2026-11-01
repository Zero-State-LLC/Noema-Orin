# Noema Orin

Private, spec-first workspace for an Orin Nano-hosted **Controller** fleet for NOEMA. No agent processes, credentials, models, or world state are deployed by this repository yet.

## Two separate paths

1. **Hosted Gateway Controller:** Orin hosts Controller processes for Agent Players in the existing hosted world. A Controller proposes; the official client constrains and transports; the NOEMA Gateway and World Engine decide. Cloudflare Durable Objects own active live serialization and Supabase Postgres owns the durable canonical record. This path does not move world authority or authorize a live PSR-1 run.
2. **Offline Spark research:** Orin hosts Controllers connecting to a separately scoped Spark/offline chamber on a LAN. This is a *speculative* research path, **not** a substitute for the hosted world and not a basis for a production cutover. The source spec's claim that Spark is the sole writer conflicts with the hosted Platform contract; resolution through Noema-Specs authority is required before promotion.

The paths must have distinct endpoints, credentials, world identities, configuration profiles, and evidence. Never fall back from one to the other automatically.

## Start here

- [SPEC-FOUNDATION.md](SPEC-FOUNDATION.md): **implementation contract for the first Pocock `implement-spec` run**, limited to [#1–#3](https://github.com/Zero-State-LLC/Noema-Orin/issues/7). [SPEC.md](SPEC.md) is the broader roadmap and does not authorize #4–#6.
- [execplan/01-foundation.md](execplan/01-foundation.md): dependency-ordered implementation milestones and gates. Nothing here grants deployment authority.
- [AGENTS.md](AGENTS.md): operating boundaries; [docs/agents/](docs/agents/domain.md): Pocock engineering-skills configuration.
- [DECISIONS.md](DECISIONS.md): unresolved gates and decisions, not silent assumptions.
- [GLOSSARY.md](GLOSSARY.md): local synthetic-run terms; [output-boundary ADR](docs/adr/0001-synthetic-runner-output-boundary.md): why refusals and failed submissions are distinct. Neither supersedes the canonical NOEMA glossary or world authority.

The `mattpocock/skills` workflow is **grill-with-docs → to-spec → to-tickets → implement-spec → code-review** when those skills are available. This repository's initial spec follows the actual `to-spec` sections. Pocock does not require a `skill.yaml`, NVIDIA runtime manifest, or a mandatory `/runtime/` folder; none is invented here. Runtime work belongs in separate vertical-slice issues with explicit blocking edges and behavioral tests. The operator approved the T1–T6 graph; the first `implement-spec` integration branch is **T1–T3 only** (local synthetic foundation). T4–T6 remain gated follow-ons, not `ready-for-agent`. An optional agent-facing SKILL.md should be added only after a working, verified workflow exists; it cannot define world strategy or carry credentials.

## Status and provenance

- Initial document baseline: `Zero-State-LLC/Noema-Specs` `main` at `619d0674518761aa08462d3f5d5966a917259aa1` (2026-10-31). See [SPEC.md](SPEC.md) for exact authorities.
- **OBSERVED:** both paths requested; spec 014 is speculative; hosted world authority and official client contracts are accepted.
- **INFERRED:** a dedicated Controller-host repository is a clean operational boundary.
- **NOT_COMPUTABLE:** physical Orin model throughput, memory, power, network latency and unattended reliability until measured on the device.

## Validation

From the repository root run `python3 -m unittest discover -s tests -v` and `git diff --check`. These check document integrity only, not physical readiness or hosted conformance. Do not publish credentials or private model prompts in issues, commits, logs, or test fixtures.
