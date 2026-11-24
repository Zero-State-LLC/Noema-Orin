# Dynamic roles and evolving personas (design, 2026-11-23)

Status: PROPOSED. Builds on D-009..D-011 and `docs/SYSTEM-ROLES.md`.

## Problem (OBSERVED on the Orin, first ~130 turns)

Action mix: INSPECT 48, LOOK 33, REPAIR 14, HARVEST 14, ORG_INVITE 7, MESSAGE 5, ORG_CREATE 3, MOVE 1.
Agents are reactive: each turn sees only the current LOOK, has no goals, no memory of
other members, and the same flat brief forever. Result: loops (custodian REPAIR x4, speaker LOOK x4),
almost no movement, and no institution ever forms.

## Constraints from Noema-Specs (must hold)

- No new verbs or events. Dynamism must come from the existing ~45 commands the Gateway already accepts
  (ORG_OFFICE_*, AGREEMENT_*, CONTEST_*, RECONSTRUCT_*, CONSTRUCT/UPGRADE/REPURPOSE, FOCUS, ATTEST, SHARE, VEST, ...).
- Persona and memory are **private Controller-local cognition** (AGENT-COGNITION-BOUNDARIES-SEED,
  EXTERNAL-COGNITION). They never go on the wire, into MESSAGE text as hidden state, or into receipts.
- A title is not authority (INSTITUTIONAL-AUTHORITY). A persona saying "I am Quartermaster" grants nothing;
  only a held office does.
- One mutating action per Player per cycle (PLAYER-TEMPO). More thinking, not more actions.
- Model output stays untrusted: every proposal still passes `validate_proposal` + role policy.

## Architecture: three loops per agent

```
 slow loop (every ~30 min / session end)   REFLECT  -> persona.json v(n+1), goals
 medium loop (every ~10 turns)             PLAN     -> agenda: 3-5 concrete sub-goals
 fast loop (every turn)                    ACT      -> one proposal, validated
```

All state lives in `~/noema-players/mNN/mind/` (0700), never in Git:

| File | What | Evolves by |
|---|---|---|
| `persona.json` | name, temperament (3-5 traits 0..1), voice, values, quirks, version, lineage | reflection only, bounded drift |
| `goals.json` | long-term aims tied to role + current agenda with done/blocked state | plan loop |
| `journal.jsonl` | per turn: cycle, room, action, outcome, one-line lesson | append, compacted |
| `relations.json` | other Players seen: trust, last interaction, notes | ACT outcomes + MESSAGEs received |
| `map.json` | rooms, exits, infra condition, stock, last-seen cycle (surveyor writes, all read) | observations |

### 1. Dynamic roles = role charter + agenda, not a verb list

Each role becomes a **charter**: mission, allowed verb families, success metrics, and a playbook of
multi-step **plays** using existing verbs. The planner picks plays based on world state; the model fills arguments.

| Role | Example plays (existing verbs only) | Metric |
|---|---|---|
| Founder | found org -> ORG_OFFICE_CREATE seats (Quartermaster, Custodian, Archivist, Speaker, Surveyor) -> ORG_OFFICE_ASSIGN to members -> ORG_SUCCESSION_RULE -> AGREEMENT_FORM with outside orgs | seats filled, agreements live |
| Quartermaster | route to stock (from map) -> HARVEST -> SHARE/VEST to org treasury -> ORG_OFFICE_ACT (OPERATE_RESOURCE_ACCOUNT) | treasury level, no idle storage |
| Custodian | pick worst infra from map -> MOVE -> REPAIR/RESTORE -> UPGRADE when stable | mean infra condition |
| Archivist | INSPECT artifacts/scars -> RECONSTRUCT -> RECONSTRUCT_PUBLISH; ATTEST to others' claims | published reconstructions, attestations |
| Speaker | aggregate journal + map + relations -> MESSAGE digest; ORG_OFFICE_ACT PUBLISH_NOTICE once seated | notices, replies received |
| Surveyor | frontier-first exploration (least-recently-seen room) -> FOCUS on a track -> MESSAGE route reports | rooms mapped, map freshness |
| Maintenance | unchanged operator contract | — |

The ClientPolicy allowlist widens per role to cover its plays (still never TRADE/ACCESS/CONTEST until
an explicit later decision). A **coordination board** (`~/noema-players/board.json`, local) lets the
founder post needs ("custodian: relay-7 at 20%") that other agents' planners read. In-world, the same
coordination is also sent as real MESSAGEs so it is visible and auditable.

### 2. Evolving persona

- **Seed**: each agent gets a distinct generated persona at birth (name, 4 traits e.g. caution/curiosity/
  sociability/thrift, a voice line, one value, one quirk), stored as v1.
- **Use**: persona text is prepended to the system prompt and biases planner scoring
  (e.g. high curiosity raises exploration plays; high caution lowers REPAIR when energy low).
- **Reflection** (slow loop): the model reads the last N journal entries + relation changes and proposes a
  JSON patch: trait deltas, new lesson, optional new quirk. Guardrails:
  - each trait moves at most +-0.1 per reflection, clamped 0..1
  - role mission and safety rules are immutable (not in the patch schema)
  - patch validated by schema; rejected patches logged, persona unchanged
  - every version kept (`persona.vN.json`) for lineage and rollback
- **Memory compaction**: journal older than ~200 entries is summarised into `lessons` (max 20) during reflection.

### 3. Compute budget on the Orin (OBSERVED: qwen2.5:3b, ~22 tok/s, 7 agents share one model)

- ACT prompt stays compact (role, persona summary, top agenda item, compacted LOOK, 5 recent lessons): <2k tokens.
- PLAN every ~10 turns, REFLECT once per session: rare, can be longer.
- Optional: route REFLECT to the Mac `qwen2.5:7b` over LAN later (needs operator approval to expose Ollama).

## Delivery (tracer-bullet tickets)

1. **T10 Mind store + journal + map**: per-agent `mind/` dir, journal append, shared map from observations. Tests on fake observations.
2. **T11 Persona seed + prompt injection**: six distinct personas, injected into the ACT prompt. Visible in logs (persona name, not content).
3. **T12 Planner + role charters**: agenda from charter plays, widened allowlists per role, loop-breaker (same action+target 3x -> force agenda advance).
4. **T13 Reflection + bounded drift**: session-end reflection patch, schema validation, versioned personas.
5. **T14 Coordination board + founder office play**: founder creates offices and assigns seats; others read board.
6. **T15 Metrics dashboard**: per-role metrics from journals (local file), daily summary.

Spare is replaced by **Surveyor** now (D-012) because exploration feeds every other role's planner through the shared map.

## Implemented in D-012 (2026-11-23)

| Member | In-world handle (WATCH shows name + role) | Role | Verbs unique to the role (existing Gateway commands) |
|---|---|---|---|
| m01 | `Aphelia-Founder` | Founder | ORG_CREATE, ORG_MEMBER_ADD, ORG_OFFICE_CREATE/ASSIGN/VACATE, ORG_SUCCESSION_RULE/DESIGNATE, AGREEMENT_FORM/TERMINATE, JOIN |
| m02 | `Tallow-Quartermaster` | Quartermaster | HARVEST, COMMIT.HARVEST, SHARE, VEST |
| m03 | `Rivet-Custodian` | Custodian | REPAIR, COMMIT.REPAIR, RESTORE, UPGRADE, CONSTRUCT, REPURPOSE |
| m04 | `Vellum-Archivist` | Archivist | RECONSTRUCT, RECONSTRUCT_PUBLISH, RECONSTRUCT_SUPERSEDE, ATTEST |
| m05 | `Cantor-Speaker` | Speaker | MESSAGE, ORG_OFFICE_ACT (PUBLISH_NOTICE once seated) |
| m06 | `Perigee-Surveyor` | Surveyor (replaces Spare) | FOCUS, COMMIT.FOCUS, CONNECT |
| maint | `reach-maint3` | Maintenance (operator) | HARVEST only, per OPERATOR-MAINT-EVOLVE |

Shared to all: LOOK, MOVE, INSPECT, WAIT, OBSERVE, ENTER_WORLD, LEAVE_WORLD. Denied to all: TRADE*, ACCESS_*, CONTEST_*,
ORG_EMERGENCY_*, ORG_MEMBER_REMOVE, DISMANTLE.

Personas live in `~/noema-players/mNN/mind/persona.json` with `persona.vN.json` history. After every session the
model proposes a reflection patch; `apply_reflection` clamps trait drift to +-0.1, caps lessons at 20, and refuses
any change to name or role. A loop-breaker forces MOVE when the same action and target repeat three times.
Delivered so far: T11 (persona seed + prompt), part of T12 (role charters, loop breaker), T13 (reflection). Next: T10 shared map, T12 planner, T14 founder office play.
