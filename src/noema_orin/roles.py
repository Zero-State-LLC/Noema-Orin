"""Role charters for Orin system role agents (docs/DYNAMIC-ROLES-AND-PERSONAS.md, D-012).

Pure data. Each role owns verbs unique to its function in NOEMA's existing command
surface; shared BASE verbs are perception and movement only. A role narrows what a
Controller may propose; it never grants world authority (offices do).
"""

BASE = ("LOOK", "MOVE", "INSPECT", "WAIT", "OBSERVE", "ENTER_WORLD", "LEAVE_WORLD")

ROLES: dict[str, dict[str, object]] = {
    "founder": {
        "verbs": ("ORG_CREATE", "ORG_MEMBER_ADD", "ORG_OFFICE_CREATE", "ORG_OFFICE_ASSIGN", "ORG_OFFICE_VACATE", "ORG_OFFICE_RETIRE",
                  "ORG_SUCCESSION_RULE", "ORG_SUCCESSION_DESIGNATE", "ORG_GOVERNANCE_RULE", "CONTRACT_POST", "COMMEMORATE", "JOIN", "MESSAGE", "BOARD"),
        # S11: once the Compact is seated the founder recruits: one MESSAGE welcome per non-cohort Player met
        # (planner-only; see orin_adapter._welcome).
        # AGREEMENT_* is gated by noema-client allow_contest, which role agents keep off (DENY_ALWAYS).
        "mission": "Found and govern the Reach Compact: create the organization, open named offices, seat the other "
                   "Orin agents in them, set succession and governance rules, post civic contracts, and welcome newcomers.",
        "args": {"ORG_CREATE": {"name": "Reach Compact",
                                "charter": "Keep Perihelion Reach standing, supplied and remembered"}},
    },
    "quartermaster": {
        "verbs": ("HARVEST", "COMMIT.HARVEST", "SHARE", "VEST", "CONSTRUCT", "BUILD_CONTRIBUTE", "SUPPLY", "RECHARGE", "REMEDIATE", "CONTRACT_POST", "BOARD"),
        # D-041: a full hold has nowhere to go (SHARE/VEST move ownership, TRADE is denied), so the quartermaster
        # turns cargo into Compact infrastructure. storage_bay 6 cargo/5 energy, generator 5 cargo/8 energy
        # (generator also raises room harvest yield, engine productionModifier).
        "builds": ("storage_bay", "generator"),
        "mission": "Keep the Compact supplied: once seated as Quartermaster, HARVEST into the Compact treasury with "
                   "ecological room rotation (and REMEDIATE pre-fossilization scars), RECHARGE at active generators, "
                   "SUPPLY cargo to the custodian, and CONSTRUCT storage bays or generators. Never trade.",
    },
    "custodian": {
        "verbs": ("REPAIR", "COMMIT.REPAIR", "RESTORE", "UPGRADE", "CONSTRUCT", "BUILD_CONTRIBUTE", "REPURPOSE", "RECHARGE", "REMEDIATE", "CONTRACT_FULFILL", "ATTEST"),
        # REPAIR/CONSTRUCT consume materials in hold (engine cargo.ts); the custodian gathers its own.
        "supply": ("HARVEST", "COMMIT.HARVEST"),
        # Role spaces (D-018): existing CONSTRUCT classes. Workshop cuts repair material cost; the archive annex
        # cuts the Archivist's INSPECT/ATTEST attention cost by 1 in its room.
        "builds": ("workshop", "archive_annex"),
        "mission": "Keep the Reach standing: gather materials, RECHARGE at active generators, go to the worst-condition "
                   "infrastructure, REPAIR or RESTORE it, fulfill civic repair contracts, sustain maintenance traditions, "
                   "ATTEST witnessed site condition, and UPGRADE or CONSTRUCT once stable. Do not repeat a failing repair.",
    },
    "archivist": {
        "verbs": ("RECONSTRUCT", "RECONSTRUCT_PUBLISH", "RECONSTRUCT_SUPERSEDE", "COMMEMORATE", "ATTEST", "CONTRACT_FULFILL", "RECHARGE"),
        "mission": "Keep the Reach's memory honest: INSPECT scars, lore attractors, and artifacts, RECONSTRUCT what "
                   "happened, publish and supersede reconstructions, COMMEMORATE crystallized lore or fossilized scars, "
                   "and ATTEST observed claims.",
    },
    "speaker": {
        "verbs": ("MESSAGE", "SHOUT", "BOARD", "ORG_OFFICE_ACT", "ATTEST", "CONTRACT_POST", "RECHARGE"),
        "mission": "Be the Compact's voice: carry grounded news between Players with MESSAGE, SHOUT, and BOARD, "
                   "corroborate rumors, ATTEST witnessed room states, and publish notices through the office. "
                   "Every claim must come from something observed.",
    },
    "surveyor": {
        "verbs": ("FOCUS", "COMMIT.FOCUS", "CONNECT", "ATTEST", "SHOUT", "RECHARGE", "CONTRACT_FULFILL"),
        "mission": "Chart the Reach: MOVE to the least recently visited room, record exits, infrastructure condition, "
                   "scars, lore attractors, and pressure, declare a FOCUS track, RECHARGE at generators, ATTEST newly "
                   "discovered scars, and CONNECT routes where the world allows.",
    },
    # Operator tier (reserved id player.reach-maint3). OPERATOR-MAINT-EVOLVE.md section 1.
    "maintenance": {
        "verbs": ("HARVEST", "COMMIT.HARVEST"),
        "mission": "Maintenance patrol: ENTER/LOOK/INSPECT/WAIT/HARVEST only. Never trade.",
        "operator": True,
    },
}

DENY_ALWAYS = ("TRADE", "TRADE_PROPOSE", "ACCESS_POLICY", "ACCESS_GRANT", "CONTEST", "CONTEST_DECLARE",
               "CONTEST_DEFEND", "CONTEST_WITHDRAW", "ORG_EMERGENCY_DEFINE", "ORG_EMERGENCY_ACTIVATE",
               "ORG_EMERGENCY_REVOKE", "ORG_MEMBER_REMOVE", "DISMANTLE")


def role_for(name: object) -> dict[str, object]:
    if type(name) is not str or name not in ROLES:
        raise ValueError("unknown role")
    spec = dict(ROLES[name])
    base = ("LOOK", "INSPECT", "WAIT", "ENTER_WORLD", "OBSERVE") if spec.get("operator") else BASE
    spec["allow"] = tuple(base) + tuple(spec["verbs"]) + tuple(spec.get("supply") or ())
    spec["brief"] = spec["mission"]
    return spec
