# Agent instructions

This public repository owns **Orin-hosted Controller operations**, not NOEMA world authority. For the completed first implementation, read `SPEC-FOUNDATION.md`, approved issues #1–#3, `GLOSSARY.md`, `DECISIONS.md`, `docs/adr/0001-synthetic-runner-output-boundary.md`, and `execplan/01-foundation.md`. The separately approved credential-free T4a proof is scoped by `SPEC-T4A.md`, issue #13, and `execplan/02-official-client-loopback.md`; it does **not** authorize issue #4's isolated-world attach. `SPEC.md` is the broader roadmap, not a grant to implement issues #4–#6. Follow canonical vocabulary in [Noema-Specs GLOSSARY](https://github.com/Zero-State-LLC/Noema-Specs/blob/619d0674518761aa08462d3f5d5966a917259aa1/GLOSSARY.md) and source pin in `SPEC.md`.

- A Controller acts for an Agent Player; it is not a Player or world writer. The hosted Gateway, Durable Objects and Postgres keep their existing authority.
- Keep hosted and offline-spark profiles, credentials and evidence separate. Never auto-failover, execute offline research against the live world, or claim production migration.
- Spec 014's Spark-writer statement conflicts with canonical hosted Platform authority. `offline-spark` execution is BLOCKED pending a canonical resolution and independent hardware evidence.
- Do not put tokens, private prompts, browser sessions or Admin credentials into code, issues, fixtures, telemetry or model context.
- Treat telemetry as telemetry, not canonical evidence; distinguish OBSERVED, INFERRED, SPECULATIVE, NOT_COMPUTABLE.
- Do not create invented Pocock manifests or a strategy-teaching skill.
- No runtime changes, deployments or new contract fields on the strength of this initial specification alone.

<!-- trail:start -->

<!-- agent-machine:start · generated: edit .agents/machine.json, then run `python3 .agents/machine.py render --write` -->

## Workflow

Agent work is a state machine (`.agents/machine.json`): `python3 .agents/machine.py status` shows where you are and what is allowed; `go STATE` moves.

**Path:** ORIENT → INTENT → SPEC → PLAN → IMPLEMENT → VERIFY → REVIEW → MERGED.
- ORIENT → IMPLEMENT when clarification, adapter or docs-only hygiene; no contract change.
- ORIENT → LIVE_ATTACH_PREFLIGHT when the task is a live attach.
- VERIFY → IMPLEMENT when checks fail.
- REVIEW → IMPLEMENT when changes requested or CI red.
- **INTENT**: Work from an approved issue.
- **SPEC**: Scope it in a `SPEC-*.md`.
- **PLAN**: Plan under `execplan/`. Use behavior-first vertical-slice tickets with explicit blockers.
- **IMPLEMENT**: Write failing tests before implementation.
- **VERIFY**: `go REVIEW` runs `bash scripts/check.sh`, `python3 .agents/machine.py check`.
- **REVIEW**: Code review.
- **LIVE_ATTACH_PREFLIGHT** (from ORIENT when the task is a live attach): Independently verify authorization, discovery, seal, scoped credential, production pin and human stop. Do not use `/play` browser automation as the canonical agent route. Then: ORIENT when not attaching.
- **APPROVED** (from AWAITING_USER when the user says yes): Do the one approved step, then record it. Then: back when done and recorded.
- **Any state → STOPPED** on a stop signal: Stop autonomous work. Then: ORIENT when the user clears the stop.
- **Any state → ESCALATED** when CI, tests or the request itself look wrong: Something looks wrong; report it instead of working around it. Then: back when reported; work can continue · ORIENT when task dropped.
- **Any state → AWAITING_USER** before a step that needs the user: Give one summary and ask once; wait for the user's own words. Then: back when the user says no or redirects.
- No standing grant in this repo (unlike Noema and Noema-Specs).

<!-- agent-machine:end -->

## Trail — repo context graph

This repo is indexed in `.trail/cache/`: small linked markdown nodes that explain each
system and carry exact file:line spans, kept in sync with the code through git.

For ANY task here — understanding how something works, finding where code lives,
or scoping a change — get context from the graph before grepping or opening
source files. Re-ask freely (it's cheap) and reuse literal identifiers you
already have (symbol, error string, file name) as the query. New to this repo?
Run `trail map` first — a token-budgeted orientation (dir clusters, hubs,
hotspots), no LLM, no key.

- Run `trail ask "<your question>" --source` → ranked nodes with the relevant
  code spans inlined (each hit's ≤8-line crux by default; `--full` for whole
  definitions when the crux isn't enough). Match the tool to the task shape:
  for understanding or editing, the top node IS the answer — cite its
  `covers:` file:line spans and edit straight from `--source`. For
  exhaustive tasks ("every occurrence / every caller of this pattern"), ranked
  results are top-N, not complete — run `trail grep "<literal>"` instead
  (exhaustive over indexed files, grouped by enclosing symbol), falling back
  to raw `grep -rn` only for unindexed files.
- `trail skeleton <file>` → every definition's signature + span, ~10× cheaper
  than reading the file; use it to skim an API surface.
- `trail callers <symbol>` gives precomputed, exact edges — who calls this.
  Add `--direction out` for what it calls, or `--depth N` to walk
  transitively for the full blast radius. For structural questions, skip
  ranking and use this directly.
- Or browse: `.trail/cache/INDEX.md` lists every node; follow the links.
- Monorepos and folders of multiple repos rank fairly across sub-projects —
  hits carry `[scope/]` labels naming which one they're from. Narrow with
  `trail ask "<task>" --in <scope>/` once you know where you're working.

If a returned span is truncated ("+N more lines"), open the file at that exact
range before finalizing. Only open source files when a node genuinely lacks a
needed detail, and then at the exact file:line the node points to — never
re-read whole files.

After big code changes, refresh the graph with `trail build` (deterministic,
no API key, $0).
<!-- trail:end -->

## Agent skills

Pocock engineering skills ([mattpocock/skills](https://github.com/mattpocock/skills)) read this configuration.

### Issue tracker

GitHub Issues on `Zero-State-LLC/Noema-Orin`, via `gh`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical roles under their default names (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `GLOSSARY.md`, `DECISIONS.md` and `docs/adr/`. See `docs/agents/domain.md`.
