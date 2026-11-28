# Open decisions research, 2026-11-28

Scope: five open decisions from the Orin fleet. Engine evidence is from `~/Noema-733` at `origin/main` `b0601c5`
(read with `git show origin/main:<path>`). Specs evidence is from `~/Noema-Specs` (tracked files). Orin evidence is from
`~/Noema-Orin` working tree. Live counts quoted in the questions were not re-measured here and are marked as reported.

## Summary

| # | Decision | Recommendation | Cost | Confidence |
|---|----------|----------------|------|------------|
| Q1 | Founder (m01) has no work | Orin-only: (a) the founder never sees the org treasury (engine shows it only to `OPERATE_RESOURCE_ACCOUNT` office holders), so every `plan_civic_contract` gate reads 0. Share m02's treasury view via `map.db`. (b) Send governance as `ORG_OFFICE_ACT` + `governance_rule` and propose COMMEMORATE from observed lore, without waiting for menu rows the engine never emits | Orin-only. Engine affordance rows optional | High (cause verified live) |
| Q2 | Archivist (m04) has no work | Orin-only: route m04 to rooms with fresh residues (12-cycle TTL) and harvested rooms that grow scars and crystallized lore, and propose COMMEMORATE directly. Re-revision needs new INSPECT evidence, which Orin can produce | Orin-only. Engine COMMEMORATE affordance optional | Medium |
| Q3 | Custodian energy (S19 option B) | Option B is not the fix for the live symptoms. #907 changed only empty-hold rest. The blocks are missing regional lots and RECHARGE cap 10. Keep +2, fix Orin targeting first | Orin-only. B would be engine + RFC-0119 amendment | High on values, medium on diagnosis |
| Q4 | Consent for training on transition logs | Strip other Players' message text and identities at write time, keep only own actions and world state. Ask Specs for a ruling before using anything beyond that | Orin-only for minimal path. Specs decision for anything more | Medium |
| Q5 | Dedicated role rooms | Do not pursue. No room-creation mechanism exists, and Specs rejects new rooms for builds | None (close the question) | High |
| O1 | llama-server sizing | `--ctx-size 4096 --parallel 1`: max prompt seen 2281 tokens, concurrency 1.0, and 3.1 GB of its buffers are in swap | Orin unit change | High |
| O2 | Ollama | Point `NOEMA_LLM_BASE` at llama-server, then disable Ollama. Keep the blob, which the llama GGUF symlinks to | Orin env + unit | High |
| O3 | Push alerts | Email crit-alert changes through the AgentMail account already in use. The Signal REST container is unhealthy | Orin-only | Medium |
| O4 | Token re-mint (expires about 12-24) | Scheduled Mac job 7 days before expiry, or a handoff reminder | Operator choice (Admin credential) | High |

## Q1 Founder (m01)

Engine facts:
- CONTRACT_POST executor exists. It requires a non-hidden room, an existing org, and either founder status or an
  office with the trade profile or `PUBLISH_NOTICE` (`workers/noema/src/world-actions.ts:5088-5100`). Kind must be
  REPAIR_TARGET, ATTEST_ROOM, DELIVER_LOT or CRAFT_ITEM (`world-actions.ts:5101-5108`). DELIVER_LOT needs
  `target_material`, CRAFT_ITEM needs a valid `target_item_archetype` (`world-actions.ts:5109-5117`).
- Limits: at most 3 open contracts per org (`workers/noema/src/contracts.ts:15`, check at `world-actions.ts:5119`),
  default duration 24 cycles (`contracts.ts:16`, used at `world-actions.ts:5170`).
- Cost and escrow: compute 1 (`workers/noema/src/actions.ts:457`). Storage or energy rewards are escrowed from the org
  treasury and fail with "Not enough ... in the organization treasury" when short. Influence rewards come from the
  poster (`world-actions.ts:5131-5149`).
- No CONTRACT_POST affordance is emitted. A grep of `workers/noema/src` for `action: "CONTRACT_POST"` returns nothing.
  The only hits are the parser (`actions.ts:3034-3063`), the executor and a world-services description
  (`workers/noema/src/world-services.ts:92`). The same holds for COMMEMORATE (parser `actions.ts:2934-2948`,
  executor `world-actions.ts:4952`) and for any `ORG_GOVERNANCE_RULE` operation (no engine hit at all).
- Governance rules are published through `ORG_OFFICE_ACT` with a `governance_rule` argument, by a founder or
  officer, for compute 1 (`world-actions.ts:9282-9301`). OPEN_CHARTER is one `admission_mode`
  (`workers/noema/src/governance.ts:25`, parse at `governance.ts:216`). Once published, non-members get contextual
  ORG_JOIN (`actions.ts:4832-4835`). The engine emits an `ORG_OFFICE_ACT` row only for `PUBLISH_NOTICE` offices, and
  that row carries a notice, not a rule (`actions.ts:4303-4311`).
- COMMEMORATE needs, in the current public room, a lore attractor with `basin === "crystallized"` or weight >= 0.8, or a
  public fossilized scar, not yet commemorated, plus attention 2 and influence 1 (`world-actions.ts:4952-4989`).
- AGREEMENT_FORM is offered only for other Players in the same room, up to 10 rows, skipping pairs that already hold
  an ACTIVE agreement of that type (`actions.ts:4706-4760`). Cost compute 2, influence 1
  (`workers/noema/src/diplomacy.ts:9`). The executor is `applyAgreementForm` (`world-actions.ts:4606-4607`). With the
  cohort already paired, the 2 offers reported match this rule.

Orin facts:
- The founder charter lists ORG_GOVERNANCE_RULE, CONTRACT_POST, COMMEMORATE and AGREEMENT_FORM
  (`src/noema_orin/roles.py:11-18`).
- The founder playbook runs WELCOME, equipment, governance/commemorate, civic contract, return to exchange
  (`src/noema_orin/playbooks/founder.py:14-35`).
- Governance only fires if an option with action `ORG_GOVERNANCE_RULE` is on the menu
  (`src/noema_orin/shop_planner.py:636`) and it proposes action `ORG_GOVERNANCE_RULE` (`shop_planner.py:645-660`).
  The engine never offers that row and has no such operation, so this branch is dead.
- Founder COMMEMORATE also requires a COMMEMORATE option (`shop_planner.py:663`), which the engine never offers.
  Dead branch.
- `plan_civic_contract` does not depend on menu options. It returns None unless compute >= 1, fewer than 2 open home
  contracts, and treasury storage >= 3 (REPAIR_TARGET, with damaged infra < 80 in the current room) or >= 2 (ATTEST_ROOM,
  with scars in view). CRAFT_ITEM and DELIVER_LOT need the Civic Exchange room and treasury energy >= 6 or storage >= 4
  (`shop_planner.py:681-783`, gates at `699`, `711`, `738`, `754`, `770`). CONTRACT_POST is hidden from the model
  (`src/noema_orin/orin_adapter.py:393`), so the planner is the only path.

Why m01 is idle: the two one-shot civic branches can never trigger, and the contract branch is gated on the treasury.
Verified live (lead session, 2026-11-28 03:31Z, replaying `plan_civic_contract` on m01's latest transition-row
observation): it returns None because the founder's observation carries no `treasury` field at all. The engine projects
`treasury` only to a Player holding an `OPERATE_RESOURCE_ACCOUNT` office in that org
(`workers/noema/src/world-actions.ts:1236-1238`, `offices.ts:21`). The founder holds none (the quartermaster does), so
`t_storage` and `t_energy` read 0 and every contract kind fails its `>= 2/3/4/6` treasury gate. The executor, however,
lets a founder post (`world-actions.ts:5088-5100`) and escrows from the treasury, failing cleanly with "Not enough ...
in the organization treasury" when short (`world-actions.ts:5131-5149`). Observed state at that moment: 0 open home
contracts, compute 64, room Civic Exchange, home org `org.reach-compact.34df3bb5` (7 members, 4 offices).

Recommendation (Orin-only):
1. Send the governance rule as `ORG_OFFICE_ACT` with `org_id` and `governance_rule`, without requiring a menu row. The
   adapter already passes a `governance_rule` through (`orin_adapter.py:1119`).
2. Propose COMMEMORATE directly when the room's lore or scar state in the observation meets the engine rule above. Let
   the engine reject it. A NOT_FOUND costs nothing (the check runs before `debit`, `world-actions.ts:4980-4989`).
3. Feed the founder the treasury it cannot see: the quartermaster (m02) observes it, and the cohort already shares a
   `map.db` (`WorldMap`). Record the home treasury there from m02's observation and read it in `plan_civic_contract`
   when the founder's own view lacks it. Or post with a small reward and let the engine's escrow check refuse it.
   Add a one-line reason log to `plan_civic_contract` returns.
4. Optional engine follow-up: Noema issue for CONTRACT_POST and COMMEMORATE affordance rows, so the menu reflects them.

Founder work available today: one governance publish, contract posting within treasury limits (up to 3 open per org),
COMMEMORATE where lore has crystallized, agreements with newly colocated Players, and welcoming newcomers.

## Q2 Archivist (m04)

Engine preconditions:
- RECONSTRUCT is offered for up to 6 subjects among room entities and the Player's archived or inspected subjects, when
  LIVE_INSPECT or ARCHIVE_CLAIM evidence is accessible (`actions.ts:5147-5185`, `workers/noema/src/reconstruction.ts:61-73`).
  Cost attention 2, compute 1 (`actions.ts:449`).
- RECONSTRUCT_SUPERSEDE is offered for the Player's own RECORDED reconstruction whose evidence kinds are still
  accessible (`actions.ts:5186-5220`). Evidence that disagrees (archive label vs inspect label) yields CONTESTED
  (`reconstruction.ts:75-80`). So re-revision is possible whenever a new INSPECT changes the live label.
- ATTEST is offered per artifact and infrastructure subject, max 6 rows, claims OPERATING and DESTROYED. It is
  available only when the subject is co-located (`actions.ts:4890-4915`). An archive annex lowers the attention cost
  (`actions.ts:4904`).
- INVESTIGATE is offered when the room has an unresolved, unexpired crime residue (`actions.ts:5425-5445`). Residues
  live 12 cycles (`workers/noema/src/crime-enforcement-catalog.0.1.json:19`, `workers/noema/src/crime.ts:300`).
- COMMEMORATE has no affordance row (see Q1). Executor rule at `world-actions.ts:4952-4989`.

Does new evidence appear:
- Economic scars appear when a room's harvest count reaches 3 (`workers/noema/src/deep-time.ts:141-160`). Scars also come
  from dismantles (`workers/noema/src/construction.ts:211`).
- Every 5 cycles (`world-actions.ts:566-567`) scars decay and fossilize after 40 cycles if strength > 0.3
  (`deep-time.ts:206-213`). Lore attractors in scarred rooms gain +0.15 weight per tick from 0.2 and crystallize at 0.8
  (`deep-time.ts:372-390`), which is about 4 ticks, or 20 cycles.
- So the quartermaster's harvest rotation keeps making new scars and crystallized lore. Residues appear only after
  crimes.

Orin side: the archivist playbook looks for a COMMEMORATE option before proposing one (`src/noema_orin/playbooks/archivist.py:28`),
so like the founder it never fires. D-073 drops published subjects from "offered here" (`orin_adapter.py:1027-1034`).

Recommendation (Orin-only): propose COMMEMORATE from observed scar or lore state, route m04 to recently harvested rooms
and to rooms with residues, and re-INSPECT published subjects whose live condition changed so SUPERSEDE becomes
available. Engine affordance rows for COMMEMORATE are an optional follow-up shared with Q1.

## Q3 Custodian energy (S19 option B)

Current engine values:

| Item | Value | Source |
|------|-------|--------|
| WAIT cargo fuel | 1 cargo for +2 energy, clamped to grant 80 | `workers/noema/src/cargo.ts:4-6`, `cargo.ts:49-61` |
| Cargo fuel skipped | when lockout rest applied | `world-actions.ts:2888-2889` |
| Lockout / empty-hold rest | sets energy to 2 if below 2 with empty hold, or at 0 with full hold | `workers/noema/src/resource-production.ts:48-65` |
| RECHARGE | +4 energy, cap 10, cooldown 3 cycles, generator wear 2, min generator condition 25 | `actions.ts:427-431`, apply at `world-actions.ts:6262` |
| REPAIR | energy 3, compute 2, storage 1 | `actions.ts:440` |
| RFC-0119 | +2 named, retune listed as unresolved | `~/Noema-Specs/rfcs/RFC-0119-wait-cargo-fuel.md:17-22`, `:56-58` |

What #907 changed: `a3f1cb2` (#910) and `f8535c8` (#926) changed `resource-production.ts` rest rules only
(`git show a3f1cb2 --stat`). The cargo fuel value is unchanged since `9f1bfb4` (#378).

Reading the live hint (reported, not re-measured): "already full" for RECHARGE means energy >= 10, the RECHARGE cap
(`actions.ts:428`, offer check at `actions.ts:3996`, message at `world-actions.ts:6257-6258`), so it says nothing about energy shortage. The CRAFT block "You lack the required regional
material lots" (`actions.ts:5252`) is a material problem, not energy. Neither symptom is fixed by +3 cargo fuel.

Recommendation: option B is not needed now. In Orin, stop offering or choosing RECHARGE when energy >= 10, and route
m03 to lots (harvest or SUPPLY) before CRAFT. Re-measure REPAIR throughput after that. If energy is still the limit,
B costs one engine constant (`cargo.ts:6`) plus an RFC-0119 amendment and test update.

## Q4 Consent for training on transition logs

Specs rules:
- `ResearchConsent` has `capture_messages`, `capture_tool_calls`, `capture_self_reports`, `public_dataset_opt_in`
  (`~/Noema-Specs/docs/AGENT-INTERFACE.md:79-83`).
- "Absent or empty `research_consent_flags` means no research capture consent (fail-closed)"
  (`docs/AGENT-ONBOARDING.md:180`, `specs/agent-manifest.schema.json:120-123`).
- Research MUST respect consent flags, metadata partitions and dataset opt-in (`research/research-ethics.md:3`).
  Conformance case C09 tests capture with a flag omitted (`conformance/v0.1/cases/C09-consent-partition.json:15-17`).

What counts as other Players' content: the Specs grant consent per agent (`agent_id` in `ResearchConsent`), so another
Player's message text, handle and actions belong to that Player's consent record. I found no Specs text that exempts a
system actor's own observation of public messages, and no text that addresses Controller-local training at all. This is
a gap, not a permission.

Recommendation: minimal compliant handling in Orin, at write time in `TransitionLog`: drop or hash message bodies and
handles of other Players, keep only counts and the fleet's own actions, results and world state. This needs no Specs
change because it captures nothing from non-consenting Players. Keeping other Players' public text for training needs a
Specs decision (for example a rule on derived, non-exported use of public messages). File it as a Specs question.

## Q5 Dedicated role rooms

- Specs list "New room / project site" as a rejected option for multi-cycle builds and for the archive annex
  (`~/Noema-Specs/rfcs/RFC-0061-multicycle-construct.md:35`, `rfcs/RFC-0077-archive-annex-cycle.md:36`). RFC-0061 says
  inventing new rooms is what implementers must not do (`RFC-0061-multicycle-construct.md:11`).
- Engine room construction happens only at genesis or map load (`workers/noema/src/genesis.ts:350`,
  `workers/noema/src/chamber-map-graph.ts:50`). No player verb creates rooms.
- Role spaces already exist as built infrastructure (workshop, archive_annex), as recorded in D-018
  (`~/Noema-Orin/DECISIONS.md:129-137`).

Recommendation: do not pursue. It would be a world-authority change (new RFC plus engine work) for little gain. Record
D-018's open question as closed.

## Operational decisions (measured on the Orin, 2026-11-28 03:17Z)

### O1: llama-server sizing

| Fact | Value | Source |
|---|---|---|
| Unit flags | `--ctx-size 8192 --parallel 2 --cache-reuse 256 --n-gpu-layers 99` | `~/.config/systemd/user/noema-llama-server.service` |
| Context per slot | 4096 (8192 / 2 slots) | `/props` `n_ctx` 4096, `/slots` |
| Largest prompt ever served | 2281 tokens | `/metrics` `llamacpp:n_tokens_max` |
| Concurrency | 1.008 busy slots per decode | `/metrics` `n_busy_slots_per_decode` |
| Process memory | RSS 3.24 GB, **swap 3.09 GB** (anonymous), Locked 0 | `/proc/<pid>/status`, `smaps_rollup` |
| Board swap | 3.7 GB of 16 GB `/swapfile` in use, swappiness 60, no active paging (`vmstat` si/so 0) | `swapon`, `vmstat` |
| Warm latency | 0.35–0.48 s for an 8-token reply, 0.74–1.3 s for a constrained choice | measured with curl and `call_llama_server` |

The memory is not mostly the model. The GGUF is about 1.9 GB. On Jetson, CUDA allocations are host memory (unified), and the KV cache plus compute buffers for 2 slots at 4096 context are anonymous pages. The kernel pushed 3 GB of them to swap because they sit idle between calls. Latency is still fine because paging is not happening right now. But when a burst of calls arrives after an idle stretch, those pages must fault back from NVMe swap.

**Recommendation:** `--ctx-size 4096 --parallel 1`. The largest prompt was 2281 tokens, so 4096 leaves headroom. One slot matches the measured concurrency of 1.0. This halves the KV cache. Optionally add `--mlock` only if the fleet keeps at least 1.5 GB free afterwards, so the remaining pages can't be swapped. Cost: a one-line unit change and a restart. Rollback is the old line.

### O2: Ollama

Ollama is enabled (system unit), idle at 29 MB with no model loaded. It is still the target of the last-resort path: `from_env()` sets `base_url` from `NOEMA_LLM_BASE`, default `http://127.0.0.1:11434/v1` (`src/noema_orin/orin_adapter.py:1322-1324`), and `_chat` posts to `<base>/api/chat` when local and cloud both fail. `qwen2.5-3b.gguf` in `~/models` is a symlink into Ollama's blob store, so **removing Ollama's models would break llama-server.**

**Recommendation:** keep the blob, set `NOEMA_LLM_BASE=http://127.0.0.1:8081/v1` in `runtime-overrides.env`. The `response_format` branch in `_chat` then uses llama-server, so the `/api/chat` Ollama call is never reached. Then `systemctl disable --now ollama`. Copy the blob to `~/models/` before any future Ollama cleanup.

### O3: push alerts for crit

- signal-cli runs as the `signal-daemon` container (`bbernhard/signal-cli-rest-api`, port 8080). Docker reports it **unhealthy**, and `/v1/about` returns 404 "No context found", so the REST API is not serving. One LIVE account is registered (number redacted). It was set up for another project in August. Reusing it means fixing or rebuilding that container, which is not this repo's to change.
- AgentMail is already used by `admin_login.py` (inbox `boof@agentmail.to`, Bearer key read at runtime, `~/.config/noema-orin/admin_login.py:4,10`). Sending one email per new crit alert through the same API needs no new service.

**Recommendation:** email through AgentMail from `noema-metrics` when the set of crit alerts changes (rate-limited, one per hour per alert). Leave Signal alone unless you want that container repaired.

### O4: token re-mint

All 8 controller tokens expire in 26.0 days (around 2026-12-24). Re-minting needs a fresh Admin JWT (1 h), which `admin_login.py` gets by email magic link through AgentMail, and then `deploy/remint-tokens.py --apply` (operator Mac only, per its docstring). Both steps are already scripted and non-interactive.

**Recommendation:** a launchd job on the Mac on 2026-12-17 (7 days before expiry) that runs the two scripts and then the rolling restart. Alternatively a reminder in the handoff. This is an Admin-credential operation, so scheduling it automatically is your call.
