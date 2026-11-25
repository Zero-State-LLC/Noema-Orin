# System roles: what Orin may run (analysis, 2026-11-23)

Sources: Noema `origin/main` 5ed9635, Noema-Specs 6e169df. Labels: OBSERVED in code/spec, RECOMMENDED = this repo's proposal.

## Four kinds of "role" (do not mix them)

| Kind | Examples | Who runs it | Orin? |
|---|---|---|---|
| **World Service** (desk) | Exchange Broker WS01, **Quartermaster WS02**, Registrar WS03, Relay Keeper WS04, Archivist WS05, Contract Clerk WS06 (`world-services.ts`) | Gateway itself, derived from room state | **No.** Specs WORLD-SERVICES.md: services are not Players; `SERVICE_PLAYER`/`NPC_PLAYER` forbidden. They "prepare" actions; the Player confirms. |
| **Office** (seat on an Organization) | Steward, Treasurer, Archivist, Envoy, Quartermaster, Surveyor, Auditor, Marshal, Speaker, Custodian (INSTITUTIONAL-AUTHORITY.md, candidate names) with profiles PUBLISH_NOTICE, OPERATE_RESOURCE_ACCOUNT, ACCESS_RESTRICTED_ARCHIVE, GRANT_ACCESS, OPERATE_NAMED_ASSET (`offices.ts`) | Any Agent Player who holds the seat | **Yes, as ordinary Agent Players** that found or join an org and get appointed. Authority comes from scopes, never the title. Only PUBLISH_NOTICE is hosted-actable today; TRADE/REPAIR via office need treasury (GC4-S2). |
| **Operator tooling** (system actors) | Maintenance patrol `reach-maint*` (Player), maint-evolve supervisor (Admin read-only), probe `tester` (Player, `test.*` only) (`ops/maint_evolve`, OPERATOR-MAINT-EVOLVE.md) | Operator host | **Yes.** Best fit for Orin. Reserved ids `reach-maint*`, `tester`, `system-*` or operator auth context mark them `system` (`ops.ts:85`). |
| **World-side directors** | World Event Director / World Steward pressure (GC10), resource production tick, deep-time scars, tempo admission, settlement, incident recover | Gateway / Durable Object, deterministic | **No.** Must stay world-side; a Controller emitting pressure would be a writer. |

## RECOMMENDED Orin role roster

Operator tier (system actors, need Admin-minted credentials):
1. **Maintenance patrol** `reach-maint3`: ENTER/LOOK/INSPECT/WAIT/HARVEST; reports damaged infra; no TRADE. The `maint_patrol.py` engine is missing from every checked host; rebuild on `noema-client` if not found.
2. **Maint-evolve supervisor**: `/ready` and settlement pulse, pack validation. Admin read-only; never inhabits.
3. **Isolated probe** `tester`: pre-flight new packs/prompts on `test.hosted-canonical.*` before patrol uses them.
4. **Digest reader** (new, read-only): pull Operator Digests / world reports into a local daily summary. No writes.

Role tier (Admin-minted system actors `player.system-<role>`, D-011; no human enrollment):
5. **Quartermaster office holder**: watches Quartermaster desk stock, HARVESTs to keep org storage stocked, reports shortages. Needs an org with OPERATE_RESOURCE_ACCOUNT.
6. **Relay steward / Custodian**: patrols infrastructure, REPAIRs within budget (OPERATE_NAMED_ASSET).
7. **Archivist**: INSPECTs artifacts, writes RECONSTRUCTION, keeps institutional record (ACCESS_RESTRICTED_ARCHIVE).
8. **Speaker / Herald**: PUBLISH_NOTICE of world reports and incidents (the only hosted office act today).
9. **Registrar-facing Founder**: creates the founding org and appoints 5-8 (ORG_CREATE, invites).
10. **Envoy / Broker**: diplomacy and TRADE proposals; last, because TRADE is vetoed for maint actors and thrash risk is high.

## Hard boundaries (OBSERVED, constitutional)
- Admin is never a Player (RFC-0120). Supervisor credentials never reach a patrol or civic agent.
- Civic agents are `live` agents; they do not count as system actors and must not use reserved ids.
- First-party Orin agents never satisfy PSR-1's independent-operator path (G-003).
- One mutating action per Player per cycle (PLAYER-TEMPO); six agents = six slots, no burst.

## Open decisions for operator
- Where `maint_patrol.py` / `maint_runner/` live, or approve a rebuild.
- Admin to mint `maint.env` and `tester.env` and the path on Orin to read them from.
- Which civic roles the 6 pending enrollments take (default: 9,5,6,7,8 + one spare).

## Live state (2026-11-25, S19)

Reach Compact `org.reach-compact.34df3bb5` (pinned in `shared/home_org`, D-029). The founder is m01 Aphelia-Founder.

| Member | Role | Office (profile) | Role verbs | Live note |
|---|---|---|---|---|
| m01 | founder | (founder) | ORG_* governance | Created Notice, Steward, Archive Keeper; seated holders; heirs designated (D-026/D-031) |
| m02 | quartermaster | Quartermaster (OPERATE_RESOURCE_ACCOUNT, D-047/RFC-0133; TRADE still client-denied) | HARVEST into treasury, SUPPLY cargo to custodian, CONSTRUCT | Treasury harvest skips the 16-slot pack (vault cap 64) |
| m03 | custodian | Steward (OPERATE_NAMED_ASSET) | REPAIR, RESTORE, UPGRADE, CONSTRUCT | **Engine-blocked**: arrives at harvest room with energy 1; HARVEST needs 2 (Noema#907 follow-up) |
| m04 | archivist | Archive Keeper (ACCESS_RESTRICTED_ARCHIVE) | RECONSTRUCT*, ATTEST | ~50% role turns (attention-bound) |
| m05 | speaker | Notice (PUBLISH_NOTICE) | MESSAGE, ORG_OFFICE_ACT | ~70% role turns; notices grounded in observed facts only (S13) |
| m06 | surveyor | none (GRANT_ACCESS denied) | FOCUS, CONNECT | energy-capped |
| maint | maintenance (operator tier) | none | HARVEST only, never MOVE (D-024) | |

Energy rules the agents follow: WAIT at energy 0 (lockout rest +2, D-030), don't WAIT for energy when WAIT can't refuel (D-033), walk toward the goal at energy 1 (D-034), stay in the room that advertises the role verb (D-035). Decide model per turn: routine menus go to Granite 4.0 H Micro, anything social, org or build to Llama 4 Scout (D-030, verdicts from `jev route-to`).
