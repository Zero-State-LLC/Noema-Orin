# Agent instructions

This public repository owns **Orin-hosted Controller operations**, not NOEMA world authority. For the completed first implementation, read `SPEC-FOUNDATION.md`, approved issues #1–#3, `GLOSSARY.md`, `DECISIONS.md`, `docs/adr/0001-synthetic-runner-output-boundary.md`, and `execplan/01-foundation.md`. The separately approved credential-free T4a proof is scoped by `SPEC-T4A.md`, issue #13, and `execplan/02-official-client-loopback.md`; it does **not** authorize issue #4's isolated-world attach. `SPEC.md` is the broader roadmap, not a grant to implement issues #4–#6. Follow canonical vocabulary in [Noema-Specs GLOSSARY](https://github.com/Zero-State-LLC/Noema-Specs/blob/619d0674518761aa08462d3f5d5966a917259aa1/GLOSSARY.md) and source pin in `SPEC.md`.

- A Controller acts for an Agent Player; it is not a Player or world writer. The hosted Gateway, Durable Objects and Postgres keep their existing authority.
- Keep hosted and offline-spark profiles, credentials and evidence separate. Never auto-failover, execute offline research against the live world, or claim production migration.
- Spec 014's Spark-writer statement conflicts with canonical hosted Platform authority. `offline-spark` execution is BLOCKED pending a canonical resolution and independent hardware evidence.
- Before a live attach, independently verify authorization, discovery, seal, scoped credential, production pin and human stop. Do not use `/play` browser automation as the canonical agent route.
- Do not put tokens, private prompts, browser sessions or Admin credentials into code, issues, fixtures, telemetry or model context.
- Treat telemetry as telemetry, not canonical evidence; distinguish OBSERVED, INFERRED, SPECULATIVE, NOT_COMPUTABLE.
- Use behavior-first vertical-slice tickets, explicit blockers, failing tests before implementation, and code review. Do not create invented Pocock manifests or a strategy-teaching skill.
- No runtime changes, deployments or new contract fields on the strength of this initial specification alone.
