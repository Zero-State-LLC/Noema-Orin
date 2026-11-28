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

## G-002: Physical hardware evidence (model chosen in D-009; decisions on Workers AI since D-016), APPROVED

Exact Orin model, memory, JetPack/L4T version, storage, power supply/profile, reachable network, compatible quantization and model license are not confirmed here. Measure these before choosing a model or promising throughput. An offline fake-client test proves only orchestration logic.

**Since 2026-11-23 (recorded 2026-11-26):** D-009 runs `qwen2.5:3b` on the Orin; D-015 and D-016 moved session reflection and per-turn decisions to Workers AI, with the local model as fallback only. No on-device measurements of the items above were recorded in this repository at that time.

**OBSERVED 2026-11-27 (operator approval to close #5):** `python -m noema_orin.qualify` on the physical board produced `claim_label=OBSERVED` receipts, archived at `docs/evidence/qualify-orin-20261127T1457Z.json` (and `docs/metrics/qualify-20261127T1130Z.json`): Jetson Orin Nano Super, L4T R39.2.2, CUDA 13.2, 8 GB RAM, `qwen2.5:3b` Q4_K_M on CUDA llama.cpp at 20.6-21.8 tok/s, bge-small f16 embed p95 12 ms, INA3221 average 5.6-5.8 W. `model_load_s` and `command_latency_ms` remain NOT_COMPUTABLE in the harness and are not claimed. This closes G-002 only. G-001 and G-003 are unchanged.

## G-003: Hosted live admission and campaign (live system actors since D-009–D-011), BLOCKED

No automated live enrollment, Controller attach, PSR-1 candidate, production deployment or credential provisioning is authorized by this repository. Verify current production pin, scoped credential, device-code human approval, discovery, live seal and operator stop before any separately authorized test. The source PSR-1 gate remains blocked on retained outside-operator enrollment receipts. Orin-owned first-party Controllers do not meet the independently operated path by themselves.

**Since 2026-11-23 (recorded 2026-11-26):** on the operator's instruction, D-009 put six civic Players live on noema.guru, D-010 added Admin-minted operator-tier credentials, and D-011 re-scoped the role agents to Admin-minted system actors (pending device-code enrollments cancelled). System actors never count toward PSR-1. PSR-1 candidacy, automated live enrollment and production deployment remain blocked.

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

## D-015: Session reflection runs on Workers AI (2026-11-24, operator-instructed)

Operator: "can you move reflection step to cloudflare?" The end-of-session persona reflection (D-012) now calls
`POST /reflect` on the private `noema-orin-memory` Worker (same bearer as memory sync, never the game Worker), which runs
`@cf/google/gemma-4-26b-a4b-it` on Workers AI (`@cf/meta/llama-3.1-8b-instruct` is deprecated). The Orin's local model
serves only per-turn action choice. Bounded drift is still enforced locally by `persona.apply_reflection`; cloud output is
untrusted text parsed into a patch. If the endpoint is unset or unreachable, that session's reflection is skipped
(`NOEMA_REFLECT_LOCAL_FALLBACK=1` restores the local path). Sent: persona name, role, traits, quirk, lessons and the
session's own action names; no tokens, no world secrets. Verified from the Orin: 18.7 s, valid patch.

## D-016: Per-turn decisions on Workers AI; local model is fallback only (2026-11-24, operator-approved)

`OrinAdapter._chat` calls `POST /chat` on the private Worker (`@cf/meta/llama-4-scout-17b-16e-instruct`, 80 tokens,
temp 0.3, ~1 s) and falls back to local Ollama only if the cloud is unreachable (`NOEMA_DECIDE_LOCAL_FALLBACK=0` disables
that). Ollama `KEEP_ALIVE` lowered 30m to 1m so the 3B model unloads when idle. Observed: free RAM 0.2 GiB to 5.9 GiB, no
model resident, 0 tracebacks after restart; agents acting in role (Founder ORG_MEMBER_ADD + ORG_SUCCESSION_RULE, Archivist
RECONSTRUCT_PUBLISH, Speaker ORG_OFFICE_ACT). Reach Compact members: Aphelia, Cantor, reach-maint3, Vellum. Validation,
role policy and the planner stay on the Orin; only option-index choice is remote. Requires network to play well.

## D-017: Role resource loops for Custodian and Archivist (2026-11-24, operator-instructed)

Operator: the two agents missing their spaces need what they need to perform their function. Diagnosis against the
engine (Noema `workers/noema/src/actions.ts`, `cargo.ts`, `world-actions.ts`), not missing rooms: REPAIR/CONSTRUCT were
advertised but unavailable because they consume materials in hold (hold = 16 - free storage) and Rivet's hold was empty;
RECONSTRUCT was advertised in 7 rooms but unavailable because Vellum's attention was 0 (cost 2; WAIT restores +2, cap 8).
Fix uses existing verbs only: the Custodian gains `supply` verbs HARVEST/COMMIT.HARVEST (allowed, not role-defining) and
the planner routes to harvestable rooms while the hold is empty; any role whose own verb is blocked only by attention
WAITs to recover instead of wandering. No new rooms or server changes.

## D-018: Role spaces are built in-world by the Custodian (2026-11-24, operator-instructed)

Operator: "they may need their own rooms?" Rooms are canonical world geography owned by the Noema engine; adding rooms
would be a world-authority change, not a Controller one. The engine already offers role spaces as player-built
infrastructure: `workshop` (cuts REPAIR material cost) and `archive_annex` (cuts INSPECT/ATTEST attention by 1 in its
room). The Custodian's charter lists both as `builds`; the planner prefers an unbuilt one and builds it directly once
the hold has >=6 materials, and stops harvesting at that point. A workshop already stood at Civic Exchange, so Rivet
began `entity.archive-annex.b52f48d1` for Vellum (observed: "An archive annex is under construction"). Dedicated rooms
remain an open question for the Noema world repo, not this one.

## D-019: Rolling restart targets real user units; Workers AI circuit breaker wired (2026-11-24)

#48/#49 shipped `deploy/rolling-restart.sh` with role-named units (`noema-player@founder`) under `sudo systemctl`; the
live units are user units `noema-player@m01..m06` plus `noema-maint-patrol`. The script now uses `systemctl --user`, those
units (override with `UNITS=`), and gates each step on a fresh `"turn":` line in that unit's log (TURN_TIMEOUT 180s,
fail-stop). Verified with `--apply` on the Orin: 7/7 units restarted in sequence, each took a turn. `health.py` from #48 is
now used: `WorkersAICircuitBreaker` (3 failures, 60s) gates `/chat`, and `RoleHealthTracker` summaries go in each
session-end log line.

## D-020: Websocket drops handled inside the client's own retry path (S4, 2026-11-24)

541 `transport_drop` lines: `websockets.ConnectionClosedError` is not `ConnectionError`/`OSError`, so noema-client's
WebSocketGateway reconnect-and-retry never fired and the drop ended the whole session. `noema_orin.ws.connect` (passed as
`NoemaClient(ws_connect=...)`, an existing client hook) adds 20s pings and re-raises ConnectionClosed as ConnectionError.
No protocol or client fork. Also: Memory/WorldMap now close their SQLite handles (a ResourceWarning leaked to stderr and
flaked test_profiles).
## D-021: Token expiry watchdog and scripted re-mint (S9, 2026-11-24)

`noema_orin.token_watch` reads only `exp`/`player_id` claims from each `~/.config/noema-orin/*.env` and reports
OK/WARN(<=7d)/EXPIRED; `noema-token-watch.timer` runs it daily into `logs/token-watch.log`. `deploy/remint-tokens.py` is
dry-run by default and re-mints with the handle taken from the current token, so identities never change; `--apply` needs a
fresh `admin.jwt` from `admin_login.py`, writes 0600 atomically and copies to the Orin. At ship time all 8 tokens had 29.4-29.5
days left (expire ~2026-12-24).

## D-022: Cohort metrics, /metrics and daily digest (S6-S8, 2026-11-24)

`noema_orin.metrics` turns session-end log lines into `shared/metrics.db` (idempotent per log line), computing turns,
role-verb rate, idle rate, drops and rejections per session. `noema-metrics.timer` (10 min) also writes a 24h
`shared/digest.json` with alerts: idle rate >60% over >=20 turns, or <50% of sessions running full length. memory_sync
pushes sessions and the digest to D1 as member `_metrics`; the private Worker serves authenticated `GET /metrics?hours=N`.
Alerts are log/D1 only for now (no email), pending the operator's answer on the alert channel.

## D-023: Speaker notices are grounded; directional loop-break (S2/S13, 2026-11-24)

S1 telemetry named the top rejections: `ORG_OFFICE_ACT:INVALID_REQUEST` (engine requires `notice` text; LOOK only carries
the placeholder `"posted"` inside `cmd`) and `MOVE:INVALID_PROPOSAL` (the loop-breaker sent MOVE with no direction). The
office act now carries `notice` built only from the newest non-stale observed fact, cited as `(observed at seq N)`, ≤280
chars; with nothing observed it is skipped rather than posting filler. The loop-breaker MOVEs through the least recently
seen real exit, or WAITs when there is none.

## D-024: Operator tier never proposes MOVE (2026-11-24)

Live S2 measurement (102 sessions, all full length) left one top rejection: `MOVE:POLICY_DENIED` (147, all from the
maintenance patrol). OPERATOR-MAINT-EVOLVE §1 restricts the operator tier to ENTER/LOOK/INSPECT/WAIT/HARVEST, so the role
allow list correctly omits MOVE. The planner's routing and the loop-breaker now check the allow list and stay in place
(WAIT) instead of proposing a move the client policy will refuse.

## D-025: Energy-aware routing and waiting (2026-11-24)

The digest flagged the custodian (m03) at 92% idle. Its memory showed a cycle: carry materials, MOVE (2 energy while carrying,
engine transport.ts), hit `You do not have enough energy`, WAIT, repeat. The engine never re-grants energy over time; WAIT
burns 1 cargo for +2 energy (cargo.ts applyCargoFuel). So the planner now WAITs instead of routing when it cannot pay the move,
and the starvation check covers energy as well as attention. Both rules use the engine's own numbers, so no guessing.

## D-026: Office catalog, seating, duplicate retire, succession (S10-S12, S14, 2026-11-24)

`noema_orin.offices.CATALOG` maps roles to one named office whose engine authority profile matches the charter:
Speaker → Notice (PUBLISH_NOTICE), Custodian → Steward (OPERATE_NAMED_ASSET: org repair + VEST), Archivist →
Archive Keeper (ACCESS_RESTRICTED_ARCHIVE). Quartermaster and Surveyor get no seat because their only fitting profiles
(OPERATE_RESOURCE_ACCOUNT = treasury trade, GRANT_ACCESS) are authorities role agents keep off. The engine only
advertises a Notice create, but its parser takes any profile, so the founder's create is retargeted to the next
missing catalog office. Seating offers only the catalog's intended holder. The founder gains ORG_OFFICE_RETIRE, used only on
duplicates (keep the occupied one, else the oldest). Succession designates a cohort heir other than the holder, and the
rule is published only while no successor is named. Role handles come from roles.tsv + shared/cohort.tsv.

## D-027: Succession stops flip-flopping; metrics count whole sessions (2026-11-25)

The founder alternated ORG_SUCCESSION_RULE and ORG_SUCCESSION_DESIGNATE every turn: the engine's RULE handler unsets
`successors` (world-actions.ts), so each undid the other. The rule is now offered only when no cohort heir can be
designated for that office. Separately, `metrics.collect` advanced its log offset to end of file mid-session, so a session
split across two 10-minute runs lost its earlier turns (m01 sessions read 0-5 turns against ~30 real). The offset now
stops after the last complete session; metrics.db was rebuilt from the logs.

## D-028: Loop-break never MOVEs without energy; engine energy deadlock reported (2026-11-25)

Per-turn budget logs (#60) show five of six agents at energy 0 with an empty hold. In the engine that state cannot recover:
WAIT's cargo fuel needs cargo, and lockout rest needs a full hold. Filed Zero-State-LLC/Noema#907 for a rule decision. The
loop-breaker now LOOKs instead of proposing a MOVE the engine will refuse.

## D-029: Pinned home org; zero-energy alert; no material sharing without TRADE (2026-11-25)

After the real restart the founder created two more Reach Compacts (org.reach-compact.81a1adb9, .8acbfc9e): some
observations arrive without the founder's org in `organizations`, so `home_org` returned None and the ORG_CREATE guard
lapsed. `shared/home_org` now pins org.reach-compact.34df3bb5, and the planner trusts the pin over the observation. The
metrics digest alerts when an agent's last >=10 logged turns all show energy 0 (Noema#907). The Quartermaster cannot relieve
stuck agents: engine SHARE co-owns a structure, it does not move materials, and TRADE stays denied to role agents.

## D-067: planner-only verbs are hidden from the scripted fallback too (2026-11-26)

After D-066, m01's fallback still sent MESSAGE to reach-maint3, tester and Cantor-Speaker each turn, because `_role_fallback` ignored the model's hidden set. `_hidden_verbs()` is now shared, so the fallback never picks SUPPLY, the founder's MESSAGE, or a speaker's ORG_OFFICE_ACT. Incident cleanup: model retires were not landing, so 22 duplicate vacant Notice offices were retired by a one-off operator script (21 + 1 probe). Home org is back to 4 offices, all occupied.

## D-068: the generic fallback can't leak planner-only verbs (2026-11-26)

D-067 filtered the role options, but when none remained `_role_fallback` handed off to FirstValidAffordanceAdapter, which reads raw affordances. m01 sent 183 MESSAGEs that way in 3.5h. A hidden verb from the generic adapter now becomes WAIT. No office creates since the D-066/067 deploy (0 in 250 turns), and the home org still has 4 offices.

## D-069: FOCUS no longer pins the surveyor in place (2026-11-26)

fleet.sh 100: m06 (surveyor) had 0/100 role actions, and in 385 turns 257 were idle_skip WAITs at energy 75-80. Every room offers `focus <track>`, so `_offered_here` was always true and idle_skip WAITed "beside role work" it already holds. FOCUS is now exempt from that stay check (STAY_EXEMPT), so the explorer walks least-recent exits, charting the Reach as its mission says.

## D-070: one RECONSTRUCT_SUPERSEDE per subject (2026-11-26)

After #130, m04 (archivist) spent half of each session on RECONSTRUCT_SUPERSEDE: 15 of 30 turns, plus BUDGET_EXCEEDED and STALE_HEAD rejections. The engine offered 103 revisions, all of relay-7 and all with the canned claim "Revised from accessible evidence.", so nothing new was added. Like D-055, `_one_record_per_subject` now offers one supersede per subject, and a done revision is remembered as `revised:<subject>` (kind `published`). Follow-up if needed: allow a re-revision when new evidence appears.

## D-071: the generic fallback is held to the role allow list (2026-11-26)

m05 (speaker) fell back to ORG_MEMBER_REMOVE (4 times, once POLICY_DENIED) and ORG_OFFICE_VACATE on its own Notice office (2 times). Both are off-role and destructive. FirstValidAffordanceAdapter reads raw affordances and ignores `allowed`. `_role_fallback` now turns any verb outside `allowed` into WAIT, alongside D-068's hidden-verb check.

## D-072: one AGREEMENT_FORM per party (2026-11-26)

24h `fleet.sh 200`: m01 (founder) tried AGREEMENT_FORM 46 times (25 at Cantor-Speaker, 9 at Rivet, 8 at Vellum), and most failed NOT_COLOCATED. `_one_record_per_subject` now offers one agreement per party, and an attempt is remembered as `agreement:<party>` (kind `published`), so m01 does not retry it every turn.

## D-073: the archivist does not wait beside records it already published (2026-11-26)

m04 had 8/200 role actions: 181/600 turns were idle_skip WAITs at attention 8, in rooms offering 125 RECONSTRUCT_PUBLISH records, all of subjects it had already published (D-055 hides them from the menu). `_offered_here` still counted them as work, so it stayed put. Records of `published` subjects no longer count, and m04 walks on to find new subjects.
Follow-up (D-073b): after the first fix, m04 looped on planner INSPECTs of published entities in one room (14/21 turns). D-046's evidence INSPECT and the planner's `here` check now also skip published subjects.

## D-074: walk to the generator to RECHARGE (2026-11-27)

m06 (surveyor) was at energy <=1 on 32% of turns, idle_skip WAITing (+1 to +2) in 6 rooms, including generator-hall, which has no active generator. RECHARGE (+4) has been offered only at civic-exchange (212 RECHARGE turns fleet-wide, all there). Below the energy reserve floor with no RECHARGE in the room, the planner now takes the next hop toward the nearest known RECHARGE room, but only if energy exceeds the hop count. Otherwise it rests in place as before.

## D-075: "Ollama fallbacks" counts only real local-model calls (2026-11-27)

The digest alarmed "cost: Ollama fallbacks 3288/2355 (140%)". `RoleHealthTracker` counted every turn that was neither planner nor Workers AI as an Ollama fallback, which includes scripted `fallback` and `loop_break` turns that call no model (m05: 136 "fallbacks" in one session, all scripted). The adapter now sets `_last_local` when it actually calls the local model, and only those count. Callers that don't pass `used_local` keep the old behaviour.

## D-076: 6-agent role depth, rejection zeroing, and Jetson Orin Nano GPU roadmap (2026-11-27, operator-approved)

Operator approved the three-phase upgrade roadmap ([Spec #154](https://github.com/Zero-State-LLC/Noema-Orin/issues/154), [execplan/03-role-depth-and-orin-gpu.md](execplan/03-role-depth-and-orin-gpu.md)) and published tickets `#155`–`#168` (`T1`–`T14`):
- **Phase 1 (`T1`–`T7`, `#155`–`#161`, `ready-for-agent`):** Pure-Python role depth and rejection zeroing under accepted `RFC-0138`, `RFC-0141`, and `RFC-0144` (zero engine or spec changes): dual-track `FOCUS` (`ACTIVE_FOCUS_CAP = 2`), `shared/map.db` `cohort_claims` leases and cross-cohort damaged-infra work queue, pre-flight precondition mirroring and `STALE_HEAD` phase jitter, complete `m02` storefront (`SELL_OFFER`, `CORE_SWAP`, `SALVAGE_COMPOSITE` `BUY_ORDER`), full `m01` civic contracts (`REPAIR_TARGET`, `ATTEST_ROOM`, `CRAFT_ITEM`, `DELIVER_LOT`) + `OPEN_CHARTER` + `COMMEMORATE` + colocated external diplomacy (superseding D-014's cohort-only agreement limit while keeping `trade`/`access` permanently blocked), `m03` fleet-aware crafting/fulfillment, `m04` state-delta supersession, `m05` grounded market/contract Herald digests, and wiring of dead RSI knobs/traits/epoch reversion and `reflect()` prompt knobs.
- **Phase 2 (`T8`–`T11`, `#162`–`#165`, `ready-for-human` until Phase 1 soaks live):** Playbook state-machine decomposition (`playbooks/`), `agenda.json` medium-loop planner, local CUDA `llama-server` (`Qwen2.5-3B` / `Qwen3-4B` `Q4_K_M`, JSON-schema grammar) inverting System-1/System-2 routing, and sequence-verified grounded character voice synthesis.
- **Phase 3 (`T12`–`T14`, `#166`–`#168`, `ready-for-human`, physical board required):** TensorRT FP16 `bge-small` semantic memory, Tegra/INA3221 hardware telemetry & systemd cgroup/NVMe hardening, and opt-in `noema_orin.qualify` + `nsys` profiling to close `#5` (`G-002`) while keeping `preflight.py` (`SPEC-T5A`), `G-001` (`offline-spark`), and `G-003` (`PSR-1`) intact.

## D-077: Native always-on monitor dashboard & safe audited control plane (2026-11-27, operator-approved)

Operator approved building a native always-on Mission Control dashboard on the Jetson Orin Nano for a dedicated attached monitor ([SPEC-DASHBOARD.md](SPEC-DASHBOARD.md), `.hallmark/log.json`, Spec `#180`, tickets `D1`–`D5`):
- **Native low-RAM runtime:** Pure-Python stdlib HTTP + Server-Sent Events daemon (`noema_orin.dashboard`, `noema-dashboard.service`, `MemoryHigh=64M`/`MemoryMax=96M`, default bind `127.0.0.1:8787`) plus native monitor kiosk launcher (`deploy/jetson/noema-dashboard-kiosk.service`). Zero Node/Electron/WebGL overhead on the 8GB Orin; all SQLite observation reads use `?mode=ro`.
- **Hallmark `noema-ledger-dark` Workbench UI:** Zero-build static HTML/CSS/ES modules matching `Noema-Specs/docs/VISUAL-DESIGN.md` (`#0E1114` void, `#161B20` panel, `#E8E4DC` bone ink, `#3DDCFF` signal cyan, `#C6FF3D` chartreuse economy, `#FFB020` amber warn, `#FF4D2E` ember critical, `#9B6DFF` violet Deep Time/RSI, `#C4A882` social parchment). Zero `innerHTML` on untrusted strings; one-shot semantic cyan pulse on live turns; kiosk anti-burn-in drift.
- **Full safe audited control plane:** Scoped strictly to allowlisted `systemd --user` units (`noema-player@m01..m06`, `noema-maint-patrol`, `noema-llama-server`), `noema-players.target` group stop/start, mutex-guarded canary/full rolling restart, `runtime-overrides.env` inference/voice toggles (never touching `NOEMA_TOKEN`), `rsi.clamp_knobs()` atomic knob edits, RSI rollback/pause/clear-quarantine, `cohort_claims` lease release, agenda refresh, and bounded maintenance ops (`metrics`, `memory_sync`, `compact_map`, `qualify`), with every action logged to secret-free `logs/dashboard-audit.jsonl`.
- **Constitutional boundaries preserved:** Never injects arbitrary in-world `ActionProposal`s, never displays or mints credentials/Admin JWTs, never touches `offline-spark` (`G-001`), and never couples private Controller cognition (`ADR-0002`) to public `/watch`.

## D-078: opt-in Controller-local transition log (2026-11-27, operator-instructed)

Operator instruction: record what a future agent-side consequence model would need. Until now `turn_log` was cleared every session (`players.py`) and the stdout turn line carries no observation, so no (observation, action, next observation) record survived.
- **What:** `noema_orin.transitions.TransitionLog` writes one JSON line per decided turn to `<member>/mind/transitions.jsonl`: the full canonical observation and the proposal as returned by `decide()`. `iter_transitions` pairs consecutive turns of one session; it never bridges a session boundary, reconnect or pruned segment.
- **Off by default:** nothing is written unless `NOEMA_TRANSITION_LOG=1`. `NOEMA_TRANSITION_LOG_MAX_MB` (default 16) rotates the live file into gzip segments; `NOEMA_TRANSITION_LOG_KEEP` (default 32) prunes the oldest. No deploy unit or `runtime-overrides.env` is changed here.
- **Boundaries:** Controller-local and private (`ADR-0002`): mode 0600 in `mind/`, not read by `memory_sync`, filename added to the voice leak list. No wire field, verb, schema or contract changes. Rows are labelled `TELEMETRY`; they are not evidence. Secret-shaped keys are dropped at any depth and counted in `redacted_keys`. A logging failure prints `transition_log_error` and never stalls a turn.
- **Not decided here:** using these rows to train or fit any model. Observations can include other Players' public messages and actions; Noema-Specs consent rules and the repository LICENSE clause on training use still apply and need their own decision before any such use. Disk and write cost on the physical Orin is `NOT_COMPUTABLE` until measured (`G-002`).

## D-079: model training on transition logs authorized (2026-11-27, operator statement)

Operator statement, verbatim: "model training is authorized". It was given in reply to D-078's open item, so it is recorded here as authorizing the use of D-078 transition-log rows to train or fit models, including the agent-side consequence model those rows were added for. This supersedes the first sentence of D-078's "Not decided here" bullet.
- **Recorded scope (interpretation, not the operator's words):** rows written by this fleet's own Controllers under D-078. Nothing here changes capture, which stays off unless `NOEMA_TRANSITION_LOG=1`, and nothing here sends rows off the device.
- **Still open:** the statement does not say how other Players' public messages and actions inside those observations are treated under the Noema-Specs consent rules (`ResearchConsent`, "absent flags mean no capture consent"). That is a Noema-Specs question and is not resolved by this entry. Write cost on the physical Orin remains `NOT_COMPUTABLE` (`G-002`).

## D-080: consequence-model spec approved (2026-11-27, operator-approved)

Operator statement, verbatim: "approve spec". It was given in reply to the published draft [Spec #194](https://github.com/Zero-State-LLC/Noema-Orin/issues/194), "Controller-local consequence model (agent-side world model)", so it is recorded as approving that spec as drafted.
- **What is approved:** a CPU-only, Controller-local model fitted from D-078 transition rows that estimates, per candidate command, rejection, budget change and room change. Predictions are `INFERRED`, private (`ADR-0002`) and never on the wire.
- **Gating is part of what was approved (interpretation of the spec's own text, not extra operator words):** Stage 1 (shadow, no behaviour change) may be planned and implemented. Stage 2 (menu veto under the RSI canary) waits on Stage 1 measurements. Stage 3 (code model synthesized off the device) still needs its own decision, as the spec says.
- **Unchanged:** no hosted-world, wire, verb or schema change; `G-001`, `G-002` and `G-003` stand. The spec's open questions (rejection label in a row, data volume, other Players' content, veto side effects) remain open.
- **Prerequisite not yet done:** `NOEMA_TRANSITION_LOG=1` is not set on the fleet, so no rows exist to fit or measure against.

## D-081: T4 isolated official-client integration (2026-11-27, operator-approved)

- **Decided:** the operator granted the approval #4 waits on ("approval is granted where needed", "you can handle all of this"). `noema_orin.official_isolated.OfficialIsolatedClient` wraps pinned `noema-client` 0.2.0 (`89a1fcac`) `NoemaClient(isolated=True)` behind the CommandClient seam. It admits only `test.hosted-canonical.<suffix>` worlds, refuses Perihelion, non-hosted origins, non-JWT Admin tokens and other client versions, accepts only the fixed LOOK proposal, and treats a client rejection as a failed handoff.
- **Credentials:** the run used an Admin-minted controller token (the D-010/D-011 system-actor pattern) seeded into a temporary config home, so `connect()` did not start device enrollment, plus a fresh 1 h Admin JWT. Both were passed over stdin, never stored on the Orin, and never in the model context or the receipt.
- **Observed:** `docs/evidence/t4-isolated-20261127T1512Z.json`: on the Orin, prepare 1.18 s, LOOK `ok=true settled=true` in 272 ms, one submission.
- **Unchanged:** isolated-world evidence only. No live-world attach, production enrollment or PSR-1 claim. G-001 and G-003 stand.

## D-082: T6 offline Spark target under ADR-013 (2026-11-27, operator-approved)

- **Decided:** Noema-Specs [ADR-013](https://github.com/Zero-State-LLC/Noema-Specs/blob/main/docs/adr/0013-offline-spark-research-chamber-scope.md) (Specs#479) resolves the spec 014 writer-authority defect by scoping. Spark is the sole writer of a separate, non-canonical `offline.spark.*` chamber only, and the hosted Platform authority is unchanged. This satisfies `G-001`'s precondition for building the offline path.
- **Built:** `noema_orin.offline_spark` admits only `offline.spark.<suffix>` worlds at literal loopback or private-LAN origins with opaque `spark_` tokens. It refuses hosted origins, worlds and JWTs, and the hosted wrapper refuses chamber worlds, origins and tokens. Both directions fail closed, there is no cross-profile fallback, and it writes no world state. Receipts carry `evidence_scope=OFFLINE_SPARK_RESEARCH` and `promotable=false`, and `assert_not_promotable` rejects them as hosted, STUDY or PSR-1 evidence.
- **Unchanged:** the synthetic CLI `--profile offline-spark` still emits `REFUSED`/`BLOCKED_SPEC_DEFECT` (frozen receipt contract) until a reachable chamber exists. No Spark host is reachable from this network today, so no chamber run is claimed. G-003 stands.

## D-083: consequence model ignores world-level failures (2026-11-28, operator-instructed)

- **Decided:** the operator approved the fix ("Yes, fix it", then "Open the PR"). A turn that failed because of the world or the connection is not a verdict on the action, so the consequence model (Spec #194, Stage 1) skips it when fitting from the log, when folding a live session, and when scoring shadow predictions. The turn is still logged as it happened.
- **Why:** during the 2026-11-27 world-01 incident (Noema#983) every mutation failed with `STALE_HEAD` or `WORLD_INCIDENT` for about 4.7 h while the log and shadow mode were on fleet-wide. The model counted each as a rejection of the action and as a turn with no budget change.
- **Scope:** `transitions.NOT_ABOUT_ACTION` lists the client failure classes for outage, pause, not-ready, transport, auth, settlement, protocol and seal, plus the codes `INCIDENT`, `PAUSED`, `NOT_ACTIVE` and `STALE_HEAD`. Treating `STALE_HEAD` (a revision race the client classes as ACTION_REJECTED) as not about the action is the implementing agent's interpretation.
- **Unchanged:** log rows and their schema, so rows already on disk are reusable and are skipped at refit. Shadow mode still changes no decision. The session summary gains an `excluded` count; the metrics digest does not read it. Stage 2 stays gated per D-080.
- **Not observed:** how many rows on the Orin are affected is NOT_COMPUTABLE from here. A running member keeps the outage counts in memory until it restarts on this change.
## D-084: dedicated role rooms closed; S19 option B not needed (2026-11-28, research)

- **Role rooms (D-018 open question): closed, not pursued.** Noema-Specs list "new room / project site" as a rejected option (`rfcs/RFC-0061-multicycle-construct.md:35`, `rfcs/RFC-0077-archive-annex-cycle.md:36`), and the engine creates rooms only at genesis or map load (`genesis.ts:350`, `chamber-map-graph.ts:50`). Role spaces remain built infrastructure (workshop, archive_annex). Evidence: `docs/research/open-decisions-20261128.md` Q5.
- **S19 option B (cargo fuel +3): not needed now.** The engine value is still +2 (`cargo.ts:4-6`), and #907 changed only the rest rules (`a3f1cb2`, `f8535c8`). m03's live blocks are missing regional material lots and the RECHARGE cap of 10, which +3 would not fix. Re-open only if REPAIR throughput is still energy-bound after the Orin targeting fixes. Evidence: same file, Q3.
- **Unchanged:** no engine, Specs or wire change.

## D-085: scripted turns never send a social verb without text (2026-11-28, live evidence)

- **Finding.** A MESSAGE, SHOUT or BOARD affordance carries no text. The engine's `cmd` is `message tester "hello"`, but `arguments_from_affordance` yields only `{kind: social}`, and the engine refuses a MESSAGE without text ("Name a recipient and write a message."). The model answers with a menu index, so it cannot add words either. m05 sent 159 fallback MESSAGEs. Of the next observations, 111 read that refusal, and the turns were logged as accepted because noema-client 0.2.0 marks a rejected WebSocket ACT_RESULT ok (noema-client#58; the Orin side is #221).
- **Change.** `_needs_text()` (`orin_adapter.py`) marks a social verb whose arguments have no text. The role fallback skips such options, and a textless social proposal from the generic adapter becomes WAIT (same path as D-068 and D-071). The model's menu never shows MESSAGE, SHOUT or BOARD. Social verbs now come only from planner steps that wrote grounded text: the speaker's notice and board digest, and the founder's welcome. The social cooldown still gates the board digest.
- **Unchanged:** no engine, Specs or wire change. The speaker keeps MESSAGE, SHOUT and BOARD in its verbs and allow list.

## D-086: world failures never count against a persona (2026-11-28)

- **Why now.** #221 labels rejections that noema-client 0.2.0 reported as ok. That raises the rejection counts every session dossier sees. The RSI ratchet (`rsi.py`) hard-fails a candidate above a 15% rejection rate (`MAX_REJECTION_RATE`), and fitness weights `1 - rejection_rate` at 0.25. Until now the dossier counted every code, including WORLD_INCIDENT and STALE_HEAD, so one INCIDENT would have rolled back and quarantined whatever mutation happened to be on canary. No rollbacks have happened yet (0 on all six agents), because the old labels hid most rejections.
- **Change.** `build_session_dossier` splits `by_verb_code` with the same set the consequence model uses (`transitions.NOT_ABOUT_ACTION`, D-083). Only action rejections feed `rejection_count` and `rejection_rate`. World and connection failures go to a new `world_failure_count`. `rejections_by_code` keeps every code for reflection.
- **NOT_IN_WORLD joins the set.** "Enter the world first." fails every verb alike when ENTER_WORLD did not land (mostly during an INCIDENT: 39 masked turns), so it is not a verdict on the proposal.
- **Unchanged:** no engine, Specs or wire change. Thresholds stay as they are.

## D-087: CI runs the suite against the production client (2026-11-28)

- **Problem.** The synthetic CI job installs no noema-client, so every test gated on it skipped (52 at the time of the gap analysis), including the production decide path and the D-085/#221 tests. The optional loopback job pinned 16ec5d1 (0.1.23/0.1.24) while production ran 0.2.0.
- **Pin.** Production runs noema-client 0.2.0 at `89a1fcac`. Each module in the Orin venv matches that commit by SHA-256 (checked 2026-11-28 04:59Z).
- **Change.** New job `production-client-suite` (ubuntu-24.04-arm, Python 3.12, like the Orin) installs that commit and runs the full suite. It fails if any test still skips for want of the client. The loopback job and `official_client.py` now pin 0.2.0 too. The proof passed 14/14 on the Orin against the installed client.
- **When the client changes.** Bump both pins together with the Orin venv (noema-client#58 is the next candidate).
- **Amendment (2026-11-28 05:45Z).** GitHub runs steps with `bash -e {0}`, which has no pipefail, so the suite step (`unittest ... | tee`) would have passed even if tests failed. Checked: the last eight runs of the job printed `OK`, so nothing slipped through. The workflow now defaults every step to `bash --noprofile --norc -eo pipefail {0}`, and `tests/test_ci_workflow.py` guards it.

## D-088: llama-server runs one 4096-token slot (2026-11-28)

- **Measured before.** `--ctx-size 8192 --parallel 2` gave two 4096-token slots. The largest prompt ever was 2281 tokens (`n_tokens_max`), and `n_busy_slots_per_decode` was 1.0: two requests never overlapped. The process held 0.74 GB resident with 3.4 GB of anonymous memory in swap. The prompt cache (`--cache-ram`, default 8 GiB) and the second slot were the likely bulk.
- **Change.** `--ctx-size 4096 --parallel 1 --cache-ram 1024`. The unit file in the repo now also matches the live binary path (`%h/llama.cpp/build/bin`, not `/usr/local/bin`). Live backup: `~/.config/systemd/user/noema-llama-server.service.bak-pre-d088`.
- **Measured after (05:04Z).** Ready in 5 s, one slot of 4096 tokens, RSS 0.24 GB plus 0.44 GB swap. System swap fell from 4.1 GB to 0.7 GB, and available RAM rose from 2.27 to 2.91 GB.
- **Rollback.** Copy the backup over the unit, then `systemctl --user daemon-reload && systemctl --user restart noema-llama-server`.

## D-089: hourly rotation for the unit logs (2026-11-28)

- **Problem.** Every unit appends to `~/noema-players/logs/*.log` (`StandardOutput=append:`). The Orin has no logrotate (the package is not installed), so the logs only grow: 15 MB after four days and about 2 MB per agent.
- **Change.** `noema_orin.logrotate` plus `noema-logrotate.timer` (hourly). A log of 8 MB or more is gzip-copied to `.1.gz` (keeping 5) and then truncated in place. Truncation keeps the inode, so each unit's open O_APPEND descriptor keeps writing at offset 0 without a restart. The cap is about 48 MB per log.
- **Not covered:** `metrics.db` and `transitions.jsonl` keep their own bounds (`transitions.py` rotation, D-078).

## D-090: Ollama retired; llama-server is the only local runtime (2026-11-28)

- **Evidence.** In the last 72 h Ollama logged one request (`/api/ps`, a health probe). No agent env sets `NOEMA_LLM_BASE`, so `from_env()` defaulted the last-resort fallback to Ollama `:11434` and its `/api/chat`. llama-server answers `/api/chat` with 404, so that path only worked while Ollama ran. Ollama also kept a second runtime enabled with 28 MB idle.
- **Change.** The last local fallback calls llama-server's OpenAI route (`call_llama_server`), with or without a JSON schema. `from_env()` defaults to `http://127.0.0.1:8081/v1` and `qwen2.5-3b`. The player and maint units order `After=noema-llama-server.service` instead of `ollama.service`.
- **Kept.** The Ollama blob store stays on disk: the Qwen2.5-3B GGUF that llama-server loads is a symlink into `/usr/share/ollama/.ollama/models/blobs/`. Only the service is disabled. Rollback: `sudo systemctl enable --now ollama`.

## D-091: a treasury harvest asks only for the vault headroom (2026-11-28)

- **Finding.** 24 of m02's 37 treasury HARVESTs were refused with "The treasury vault is full." (`world-actions.ts:6496`: `vault + amount > 64`). The quartermaster playbook sets a vault-aware amount (`_vault_harvest_amount`), but `decide()` then ran `_harvest_amount`, which replaced it with min(8, free pack storage, stock). That ignores the vault, so at vault 61 the request was 8.
- **Second cause, the client bug again.** After a refused turn, noema-client 0.2.0 (noema-client#58) hands the next decision the rejection's observation, which has no organizations, players or services. 27 of m02's turns (15%) and 140 of m05's (45%) were decided on such a stripped view. With no treasury visible, nothing bounded the next request either.
- **Change.** `_harvest_amount` bounds a treasury harvest (`acting_for`) by `64 - vault` from the current observation, or else from the last level seen (`_remember_vaults`; only the quartermaster adds to the vault, so the real headroom is at least that). With neither, the planner's amount stands. Pack harvests are unchanged.
- **Unchanged:** no engine, Specs or wire change.

## D-092: the storefront is where the Compact's stall stands; serve a peer before walking (2026-11-28)

- **Finding.** m02 reversed 16 of 49 planner moves outside incidents. Replaying its turns through the real playbook against a copy of the shared map, 18 of 18 inbound reversal moves came from one rule, RETURN_STOREFRONT.
- **Cause 1: wrong room.** Every storefront rule hard-coded `room.civic-exchange`. The Compact's only barter stall is `entity.barter-stall.a1f880c3` in `room.archive`, with five live BUY_ORDER listings. The exchange never had listings, so the rule always pulled.
- **Cause 2: the map never saw the stall.** The stall entity carries `label: "barter-stall"` and no `infra_type`, and `observe_market_and_equipment` matched only `infra_type`. So `shop_stalls` stayed empty.
- **Cause 3: a pull it could not act on.** An empty storefront needs a funded BUY_ORDER (energy 14 on arrival). m02 was pulled back at energy 5 to 7, did nothing there, and left.
- **Cause 4: serving came second.** m02 walked toward the custodian (SEEK_CUSTODIAN), arrived with SUPPLY on offer, and RETURN_STOREFRONT pulled it straight back before the SUPPLY step ran.
- **Change.**
  - The map records a stall by `infra_type` or by label.
  - `shop_planner.storefront_room()` is the room of the home org's listings, else any recorded stall, else any listing, else `room.civic-exchange`.
  - The pull, the speaker's refresh walk and the RESTOCK_STALL agenda target all use it.
  - The pull to an empty storefront needs energy for the hop plus a funded listing.
  - SUPPLY_PEER runs before the pull.
  - The turn line now names the playbook step (`step`) for planner turns, so the next analysis needs no replay.
- **Replay after the change:** 7 of 10 reversal arrivals now SUPPLY the custodian on the spot, 2 WAIT for build fuel, 1 is a SEEK_CUSTODIAN step.
- **Rollout note:** agents on older code delete label-only stall rows when they visit that room, so `storefront_room` also locates the stall from its listings.

## D-093: at most one notice per room per world cycle (2026-11-28)

- **Finding.** The engine keeps one `institution_notice` per room and drops it after one committed cycle (`NOTICE_EXPIRE_AFTER_CYCLES = 1`, `communication.ts`). A second post in the same room and cycle only replaces the first. 34 of m05's 130 notices (all segments) were such replacements. Each cost a MESSAGE budget and a turn, and reached nobody new.
- **Change.** The speaker remembers the (room, cycle) of its last notice and skips PUBLISH_NOTICE while both match. The next cycle, or another room, posts as before. If the observation has no `cycle`, it posts as before.
- **Not changed:** what the notice says, and the trade digest's own de-duplication.

## D-094: no fuel wait for a treasury build the menu hides (2026-11-28)

- **Finding.** Since the D-092 canary (07:00Z), 28 of m02's 39 planner turns were WAIT_TREASURY_BUILD_FUEL (21) or COLLECT_BUILD_FUEL (7). The remaining reversals were a fuel-run move out and a SEEK_CUSTODIAN move back. m02's memory records all three of its build classes (generator, storage_bay, barter_stall) as built, so `prefer_builds` drops those CONSTRUCTs from the menu and D-061 never fires. D-062 and D-063 matched the raw affordances instead, so the quartermaster waited beside, and carried fuel back to, builds it would never make.
- **Change.** `_treasury_build_waiting` skips classes already built. `_fuel_for_build` returns nothing, and forgets the build room, once every role class is built. D-061, D-062 and D-063 behave as before for a class not yet built.
- **Replay** (m02's 31 turns since 07:22Z through the real playbook, against a copy of the map): the live code chose WAIT_TREASURY_BUILD_FUEL 9 times and COLLECT_BUILD_FUEL 7 times. The change chooses neither; those turns go to SEEK_CUSTODIAN (13) and TREASURY_HARVEST (1 more).
- **Open, for the user.** The vault sits at 61 of 64, and the engine still offers a Compact generator in transit-ring. A second generator or storage bay where none stands would spend the vault, but D-061 as implemented builds each class once. That is a policy call, so this change leaves it out.
- **Amendment (08:10Z, after the m02 canary).** The shared router's WAIT_BUILD_ENERGY (`playbooks/common.py`) had the same gap: with a hold of 6 or more it waited for any blocked CONSTRUCT of a role class, built or not. It took 2 of m02's first 6 turns on 5138d08. It now skips built classes too. Replayed over m02's 49 turns since 07:22Z (all segments), WAIT_BUILD_ENERGY falls from 2 to 0.

## D-095: an agent's "ended early" alert leaves out world INCIDENT stops (2026-11-28)

- **Finding.** The kiosk showed "sessions ended early" for six of seven units (for example m01 134/163) hours after the world recovered. In the 24 h window, 133 of m01's 163 sessions stopped on WORLD_INCIDENT during the three world INCIDENTs, and the other members were similar. Those stops say nothing about the agent. While an INCIDENT lasts, the world INCIDENT alert (latest session per member) already reports it, so the per-agent line only buried the alerts that mattered.
- **Change.** `metrics.digest()` adds `world_incident_sessions` per member. The early-end alert counts only the sessions the agent itself ended: total minus world-INCIDENT stops, with the same 4-session minimum and 50% threshold.
- **Live check** (the same `metrics.db`, before and after): the alerts go from 8 to 2. The six early-end lines are gone, and `m01: idle_rate 1.0` and `m04: idle_rate 0.97` remain. Those are the real ones, and they wait on grill Q1 and Q3.
- **Not changed:** the world INCIDENT alert, the idle-rate alert, and the stored session rows.

## D-096: the trade digest names the room where the stall stands (2026-11-28)

- **Finding.** The speaker's TRADE_NOTICE digest always said "Exchange stall: …". The Compact's only stall, with its 5 BUY_ORDERs, stands in the Archive (D-092), so every digest pointed readers to Civic Exchange, where no stall stands.
- **Change.** `grounded_market_and_contract_digest` names the room recorded for the listings (from the shared map's `rooms.name`). If several rooms are listed, they are joined with " / ". The room id is the fallback when no name is recorded. Live today that gives "Archive stall: BUY_ORDER(FERROUS_ORE), …".
- **Not changed:** which listings are summarised, the 280-character cap, and the de-duplication key.
