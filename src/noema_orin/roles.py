"""Role charters for Orin system role agents (docs/DYNAMIC-ROLES-AND-PERSONAS.md, D-012).

Pure data. Each role owns verbs unique to its function in NOEMA's existing command
surface; shared BASE verbs are perception and movement only. A role narrows what a
Controller may propose; it never grants world authority (offices do).
"""

BASE = ("LOOK", "MOVE", "INSPECT", "WAIT", "OBSERVE", "ENTER_WORLD", "LEAVE_WORLD")

ROLES: dict[str, dict[str, object]] = {
    "founder": {
        "verbs": ("ORG_CREATE", "ORG_MEMBER_ADD", "ORG_OFFICE_CREATE", "ORG_OFFICE_ASSIGN", "ORG_OFFICE_VACATE", "ORG_OFFICE_RETIRE",
                  "ORG_SUCCESSION_RULE", "ORG_SUCCESSION_DESIGNATE", "ORG_GOVERNANCE_RULE", "CONTRACT_POST", "COMMEMORATE", "JOIN",
                  "AGREEMENT_FORM", "AGREEMENT_TERMINATE", "ASSIGN_STEWARD", "EQUIP", "UNEQUIP", "USE_ITEM", "CONTEST_DEFEND",
                  "MESSAGE", "BOARD"),
        "mission": "Found and govern the Reach Compact: create the organization, publish an OPEN_CHARTER governance rule, "
                   "open named offices, seat the other Orin agents in them, maintain escrowed civic contracts, commemorate "
                   "crystallized lore, form mutual agreements, and welcome newcomers.",
        "args": {"ORG_CREATE": {"name": "Reach Compact",
                                "charter": "Keep Perihelion Reach standing, supplied and remembered"}},
    },
    "quartermaster": {
        "verbs": ("HARVEST", "COMMIT.HARVEST", "SHARE", "VEST", "CONSTRUCT", "BUILD_CONTRIBUTE", "SUPPLY", "RECHARGE", "REMEDIATE",
                  "CONTRACT_POST", "CONVERT", "TRADE", "EQUIP", "UNEQUIP", "USE_ITEM", "SCRAP_ITEM", "ASSIGN_STEWARD", "BOARD"),
        # D-041 + RFC-0140/0141: builds storage bays, generators, and the Compact barter_stall at Civic Exchange;
        # storefront TRADE phases (stock/withdraw/list/unlist) are strictly planner-only (_hidden_verbs).
        "builds": ("barter_stall", "storage_bay", "generator"),
        "mission": "Keep the Compact supplied: HARVEST into the Compact treasury with ecological room rotation, "
                   "operate the Reach Compact barter_stall at Civic Exchange via deterministic storefront listings, "
                   "recycle depleted_cell cores at generators, SUPPLY cargo to needy cohort peers, and CONSTRUCT "
                   "barter stalls, storage bays, or generators.",
    },
    "custodian": {
        "verbs": ("REPAIR", "COMMIT.REPAIR", "RESTORE", "UPGRADE", "CONSTRUCT", "BUILD_CONTRIBUTE", "REPURPOSE", "RECHARGE",
                  "REMEDIATE", "CONTRACT_FULFILL", "CRAFT", "REFINE", "EQUIP", "UNEQUIP", "USE_ITEM", "SCRAP_ITEM",
                  "FOCUS", "COMMIT.FOCUS", "CONTEST_DEFEND", "ATTEST"),
        # REPAIR/CONSTRUCT/CRAFT consume materials in hold (engine cargo.ts); the custodian gathers its own.
        "supply": ("HARVEST", "COMMIT.HARVEST"),
        # Role spaces (D-018): workshop cuts repair/craft cost; archive_annex cuts Archivist attention cost.
        "builds": ("workshop", "archive_annex"),
        "mission": "Keep the Reach standing: gather materials, RECHARGE at active generators, fabricate tools and power cells "
                   "at workshops (focusing engineer and artificer), REPAIR or RESTORE damaged infrastructure, fulfill civic "
                   "contracts, remediate pre-fossilization scars, ATTEST witnessed site condition, and UPGRADE or CONSTRUCT.",
    },
    "archivist": {
        "verbs": ("RECONSTRUCT", "RECONSTRUCT_PUBLISH", "RECONSTRUCT_SUPERSEDE", "COMMEMORATE", "ATTEST", "CONTRACT_FULFILL",
                  "RECHARGE", "INVESTIGATE", "CONTEST_DEFEND", "FOCUS", "COMMIT.FOCUS", "EQUIP", "UNEQUIP", "USE_ITEM"),
        "mission": "Keep the Reach's memory honest: INSPECT scars, lore attractors, and artifacts, INVESTIGATE crime residues, "
                   "defend public artifacts via CONTEST_DEFEND, RECONSTRUCT what happened, publish and supersede "
                   "reconstructions, COMMEMORATE crystallized lore or fossilized scars, and ATTEST observed claims.",
    },
    "speaker": {
        "verbs": ("MESSAGE", "SHOUT", "BOARD", "ORG_OFFICE_ACT", "ATTEST", "CONTRACT_POST", "RECHARGE", "FOCUS", "COMMIT.FOCUS",
                  "EQUIP", "UNEQUIP", "USE_ITEM"),
        "mission": "Be the Compact's voice: carry grounded news between Players with MESSAGE, SHOUT, and BOARD, "
                   "publish grounded TRADE_NOTICE digests of active barter_stall stock and open contracts, corroborate "
                   "rumors, and ATTEST witnessed room states. Every claim must come from something observed.",
    },
    "surveyor": {
        "verbs": ("FOCUS", "COMMIT.FOCUS", "CONNECT", "ATTEST", "SHOUT", "RECHARGE", "CONTRACT_FULFILL", "HARVEST", "COMMIT.HARVEST",
                  "CONTEST_DEFEND", "SANCTION", "INVESTIGATE", "EQUIP", "UNEQUIP", "USE_ITEM", "TRADE"),
        "mission": "Chart and guard the Reach: MOVE to the least recently visited room, map lots, stalls, scars, lore "
                   "attractors, and open contests into shared memory, harvest edge salvage, defend Compact assets via "
                   "CONTEST_DEFEND and evidence-backed SANCTION (never declare offensive contests), and CONNECT routes.",
    },
    # Operator tier (reserved id player.reach-maint3). OPERATOR-MAINT-EVOLVE.md section 1.
    "maintenance": {
        "verbs": ("HARVEST", "COMMIT.HARVEST"),
        "mission": "Maintenance patrol: ENTER/LOOK/INSPECT/WAIT/HARVEST only. Never trade.",
        "operator": True,
    },
}

# Strictly offensive / unbounded verbs permanently denied across every Orin unit (RFC-0141 §1-2).
DENY_ALWAYS = ("TRADE_PROPOSE", "ACCESS_POLICY", "ACCESS_GRANT", "CONTEST", "CONTEST_DECLARE",
               "CONTEST_WITHDRAW", "ORG_EMERGENCY_DEFINE", "ORG_EMERGENCY_ACTIVATE",
               "ORG_EMERGENCY_REVOKE", "ORG_MEMBER_REMOVE", "DISMANTLE")


def role_for(name: object) -> dict[str, object]:
    if type(name) is not str or name not in ROLES:
        raise ValueError("unknown role")
    spec = dict(ROLES[name])
    base = ("LOOK", "INSPECT", "WAIT", "ENTER_WORLD", "OBSERVE") if spec.get("operator") else BASE
    spec["allow"] = tuple(base) + tuple(spec["verbs"]) + tuple(spec.get("supply") or ())
    spec["brief"] = spec["mission"]
    return spec
