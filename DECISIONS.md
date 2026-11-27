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

## G-002: Physical hardware evidence (model chosen in D-009; decisions on Workers AI since D-016), NOT_COMPUTABLE

Exact Orin model, memory, JetPack/L4T version, storage, power supply/profile, reachable network, compatible quantization and model license are not confirmed here. Measure these before choosing a model or promising throughput. An offline fake-client test proves only orchestration logic.

**Since 2026-11-23 (recorded 2026-11-26):** D-009 runs `qwen2.5:3b` on the Orin; D-015 and D-016 moved session reflection and per-turn decisions to Workers AI, with the local model as fallback only. No on-device measurements of the items above are recorded in this repository yet, so this gate stays NOT_COMPUTABLE.

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
