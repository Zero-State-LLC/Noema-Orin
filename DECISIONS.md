# Decisions and gates

## D-001: Two isolated Controller targets (2026-10-31)

Operator selected **both paths, explicitly separate, with no live-world cutover**. The `hosted` profile retains Cloudflare Durable Objects live serialization and Supabase Postgres canonical durability. The `offline-spark` research profile remains a separate target. Neither profile is a fallback for the other.

## D-002: Private initial repository (2026-10-31)

Operator selected private visibility for repository bootstrap. On 2026-10-31 the operator requested public visibility to run CI and finish the synthetic foundation; the repository was changed to public and verified via the GitHub API. Public visibility is not permission to store credentials or private prompts in Git. Historical issues, PRs, commits and Actions logs are publicly accessible; avoid publishing secrets in any of them.

## D-003: Reuse the official client (2026-10-31)

Accepted RFC-0116 identifies `scrimshawlife-ctrl/noema-client` as the official first-party Controller package. This repository integrates that package instead of forking it or introducing another Player class. A scripted adapter is sufficient for a first executable proof; a specific NVIDIA model is not a prerequisite. Read-only API inspection at `noema-client` v0.1.23 (`16ec5d1f472295055439975f88567a43fe6ee3b0`) found `NoemaClient.act(ActionProposal)` and an injectable HTTP transport, not the synthetic `CommandClient.submit(Mapping)` interface. The foundation remains stdlib-only and supports Python >=3.10; the inspected official client requires Python >=3.11. Issue #4 must own the tested translation and interpreter decision. Fake/local integration is feasible without credentials, but real isolated attach remains separately authorized and cannot be inferred from that proof.

## D-004: Synthetic foundation outcome boundary (operator-confirmed)

For issues #1–#3 only, validate profile before fixture, adapter, or client; reject blocked/unknown/missing profiles before reading any fixture. At the injectable runner boundary, only plain `str` profiles and plain `dict` fixtures/observations/proposals with plain `str` keys are accepted: subclass overrides must not fabricate a valid marker or action. A bad hosted fixture refuses before adapter/client, and an invalid proposal refuses before client. Each invocation emits one allowlisted JSON record on stdout with no raw input or exception on either stream. `REFUSED` means no submission; `FAILED_SUBMISSION` means exactly one failed hosted handoff, nonzero exit, no retry or cross-profile fallback; `ATTEMPTED` means one successful fake handoff but never world acceptance or settlement. See `SPEC-FOUNDATION.md`, `GLOSSARY.md`, and `docs/adr/0001-synthetic-runner-output-boundary.md`. This does not authorize live execution, physical-device claims, or offline Spark.

## D-005: Credential-free official-client loopback proof (2026-10-31)

The operator approved a separate T4a slice at [spec #12](https://github.com/Zero-State-LLC/Noema-Orin/issues/12) and [ticket #13](https://github.com/Zero-State-LLC/Noema-Orin/issues/13): reuse the synthetic `CommandClient.submit` runner seam via an optional adapter to pinned `noema-client` v0.1.23 `NoemaClient.act(ActionProposal)` on Python >=3.11. The adapter is a **loopback-only proof**, not a live client route: explicit `127.0.0.1` origin, temporary config, scrubbed selectors, real client and pinned client's fake server. The existing Python >=3.10 package, CLI and receipt contract remain unchanged. A false `CommandResult.ok` and client rejection are failed handoffs, never accepted results; client setup must finish before the runner may submit. `connect()` already enters and observes on the fake world, so do not issue a redundant observation command. Fixture enrollment tokens never enter the scripted model or receipt. This decision does not lift #4's human authorization gate, #5's hardware gate, or #6's canonical writer-authority gate.

## G-001: Offline authority defect, BLOCKED

Spec 014 is SPECULATIVE. Its statement that Spark is the sole WorldState writer conflicts with `Noema-Specs/CONTEXT.md` for the hosted Platform. Before offline execution or any promotion, record a canonical decision that explicitly scopes Spark to a non-canonical offline chamber, defines its identity and interfaces, and states what evidence can and cannot be promoted. Do not edit the source spec in this repository or call the defect resolved.

## G-002: Physical hardware evidence, NOT_COMPUTABLE

Exact Orin model, memory, JetPack/L4T version, storage, power supply/profile, reachable network, compatible quantization and model license are not confirmed here. Measure these before choosing a model or promising throughput. An offline fake-client test proves only orchestration logic.

## G-003: Hosted live admission and campaign, BLOCKED

No automated live enrollment, Controller attach, PSR-1 candidate, production deployment or credential provisioning is authorized by this repository. Verify current production pin, scoped credential, device-code human approval, discovery, live seal and operator stop before any separately authorized test. The source PSR-1 gate remains blocked on retained outside-operator enrollment receipts. Orin-owned first-party Controllers do not meet the independently operated path by themselves.

## G-004: Pocock ticket graph, APPROVED FOR PUBLICATION

The operator approved T1–T6 granularity and blocking edges for publication on 2026-10-31. This approval concerns the **issue graph only**. T1–T3 may be marked `ready-for-agent` for local synthetic work; T4 isolated integration, T5 physical access and T6 offline-Spark authority retain their explicit gates. No ticket label authorizes production attach, deployment or a canon change.

## D-006: Controller group scope (2026-11-23, operator-confirmed)

"Agent cohort" on Orin means a **Controller group**; "cohort" stays reserved for PSR-1. First dry-run target is 6 synthetic members, live counts gated on #5. Decisions come first from a remote LLM by wrapping `Noema-733/clients/noema-llm-agent` behind `DecisionAdapter`, with all proposals passing the existing validator (LOOK-only until widened); on-device inference is a later experiment after #5. Each member has its own Agent Player, credential slot and receipt stream. #5 may start now if the board is reachable.

## D-007: Group operation rules (2026-11-23, operator-confirmed)

Board reached via a key-only `orin` SSH alias (address pending from operator). First remote decision backend is a LAN Ollama server over the OpenAI-compatible API; paid APIs are opt-in with keys from the secret store. Member failures are isolated: no retry, others continue, group exits nonzero. One SIGTERM to the supervisor is the group stop and is tested in dry runs. Foreground only; any systemd unit is a separate ticket after #4/#5.

## D-008: LAN decision backend (2026-11-23, operator-confirmed)

Ollama on the operator Mac serves `qwen2.5:7b` to the LAN over the OpenAI-compatible API. The endpoint lives only in local hosted-profile config, never in fixtures, receipts or Git.

## D-009: Persistent civic Players on noema.guru (2026-11-23, operator-instructed)

Operator instructed: "the agents should be running as persistent players in noema.guru" and "you can do all of this". This supersedes D-006/D-007's dry-run-only and foreground-only limits **for the six civic members only**. Each member is an ordinary Agent Player enrolled by the official `noema-client` device-code flow (human approves on `/connect`), with its own config dir, credential and receipts under `~/noema-players/mNN/`. Roles (docs/SYSTEM-ROLES.md) narrow each member's ClientPolicy; no member may TRADE, grant ACCESS or CONTEST. Decisions come from Ollama on the Orin itself (`qwen2.5:3b`), so no LAN model endpoint is exposed. Members run as `systemd --user` units `noema-player@mNN` under `noema-players.target`; `systemctl --user stop noema-players.target` is the group stop. Operator-tier system actors (maintenance patrol, supervisor, tester probe) remain gated on Admin-minted credentials. This does not satisfy PSR-1's independent-operator path (G-003).

## D-010: Operator tier on Orin (2026-11-23, operator-instructed)

Admin session obtained by magic link to locked mailbox `boof@agentmail.to`, read through the AgentMail API (key in macOS keychain `agentmail-api`). The Admin JWT stays on the operator Mac (`~/.config/noema-orin/admin.jwt`, 0600, 1h) and never reaches the Orin or any Player command. Admin minted two 30-day agent Controller tokens for reserved system ids `player.reach-maint3` and `player.tester`, stored on the Orin at `~/.config/noema-orin/{maint,tester}.env` (0600) and loaded only via systemd `EnvironmentFile`. `noema-maint-patrol` runs the maintenance role (ENTER/LOOK/INSPECT/WAIT/HARVEST). `noema-supervisor.timer` runs upstream `ops/maint_evolve` every 5 minutes against public `/ready` only. The `tester` probe is staged but not scheduled: it must target an admitted `test.hosted-canonical.*` world. The original `maint_patrol.py` engine was not found; the patrol is the Orin player runner with the maintenance role. Local Ollama decisions are compacted to fit a 3B model, with a scripted fallback.

## D-011: Role agents are Admin-minted system actors (2026-11-23, operator-instructed)

Operator: "for the system agents, since they will be exclusively handled by the orin, we can bypass the human enrollment step." The six role agents are re-scoped from device-enrolled live agents (D-009) to **system actors** with reserved ids `player.system-{founder,quartermaster,custodian,archivist,speaker,spare}`, minted by Admin `/v1/admin/controller-token` (30-day TTL) and loaded via `EnvironmentFile=~/.config/noema-orin/mNN.env` (0600). Server classifies `system-*` as system actors (`ops.ts` isReservedSystemActorId), so they are excluded from the live-agent census and never count toward PSR-1. Pending device-code enrollments were cancelled. Token rotation requires a fresh Admin session; run `~/.config/noema-orin/admin_login.py` then re-mint before day 30.

## D-012: Themed personas, role-unique verbs, Surveyor (2026-11-23, operator-instructed)

Operator: personas need names fitting the game's theme; the game should show name and role; roles may have verbs
unique to their function; spare needs a unique role. Each role agent now has a Perihelion-Reach-themed persona and an
Admin-minted handle `<Name>-<Role>` (Aphelia-Founder, Tallow-Quartermaster, Rivet-Custodian, Vellum-Archivist,
Cantor-Speaker, Perigee-Surveyor). The earlier `system-*` tokens (D-011) are unused and expire on their own.
Admin issuance keeps them system actors (`ops.ts` actorKindFromPrincipal: `issued_by=admin`). Spare is replaced by
Surveyor. Role verb sets are drawn only from existing Gateway commands; no new verbs. Persona state is private Controller-local
cognition and never goes on the wire.

## D-013: Controller-local SQLite memory, Cloudflare as backup only (2026-11-24, operator-approved)

Issue #31. Agent memory lives on the Orin: one `mind/memory.db` per agent (facts with `source_sequence`, FTS5 recall,
stale marking when observation contradicts, relation evidence never collapsed) plus a shared `shared/map.db` (rooms,
exits, offered actions) and `shared/cohort.tsv` (Orin player ids). Grounds: AGENT-HARNESS §21 says harness memory is
Controller-local, not world authority; v0.7 requires no vector DB; the Orin has ~0.5 GiB free, ruling out ChromaDB (~380 MB
RSS). sqlite-vec can be added to the same file later. Cloud: a private Worker + D1 (never the game Worker) receives
background replication (T20, #36) for durability; turns never wait on the network. A deterministic planner sits in front
of the 3B model: no ORG_CREATE once a home org exists, org acts only on the oldest founded org, invites limited to the
Orin cohort, routing toward rooms offering role verbs. Turns are staggered: cooldown = max(cooldown, 8s x cohort) with
per-member start offsets.

## D-014: Private D1 memory mirror live; agents play as themed handles (2026-11-24)

T20 (#36): Worker `noema-orin-memory` (workers.dev, bearer `SYNC_TOKEN`, keychain `noema-orin-memory-sync`, Orin
`~/.config/noema-orin/memory-sync.env` 0600) with D1 `noema-orin-memory`. `noema-memory-sync.timer` pushes changed rows every
5 min from read-only local opens; marks advance only after 2xx. Not bound to the game Worker. Stale `resume_token`s were
reconnecting agents as `player.system-*`; they were cleared so agents now play as `player.<Name>-<Role>`. The
system-founder's 13 Reach Compacts are orphaned history; Aphelia founds one fresh org. Agreements are limited to the Orin cohort
and never trade/access. OpenClaw gateway user unit disabled at operator request.
