"""Role charters for Orin system role agents (docs/DYNAMIC-ROLES-AND-PERSONAS.md, D-012).

Pure data. Each role owns verbs unique to its function in NOEMA's existing command
surface; shared BASE verbs are perception and movement only. A role narrows what a
Controller may propose; it never grants world authority (offices do).
"""

BASE = ("LOOK", "MOVE", "INSPECT", "WAIT", "OBSERVE", "ENTER_WORLD", "LEAVE_WORLD")

ROLES: dict[str, dict[str, object]] = {
    "founder": {
        "verbs": ("ORG_CREATE", "ORG_MEMBER_ADD", "ORG_OFFICE_CREATE", "ORG_OFFICE_ASSIGN", "ORG_OFFICE_VACATE",
                  "ORG_SUCCESSION_RULE", "ORG_SUCCESSION_DESIGNATE", "JOIN"),
        # AGREEMENT_* is gated by noema-client allow_contest, which role agents keep off (DENY_ALWAYS).
        "mission": "Found and govern the Reach Compact: create the organization, open named offices, seat the other "
                   "Orin agents in them, set a succession rule.",
        "args": {"ORG_CREATE": {"name": "Reach Compact",
                                "charter": "Keep Perihelion Reach standing, supplied and remembered"}},
    },
    "quartermaster": {
        "verbs": ("HARVEST", "COMMIT.HARVEST", "SHARE", "VEST"),
        "mission": "Keep the Compact supplied: find stock, HARVEST when stock and storage allow, and SHARE or VEST "
                   "resources into the organization rather than hoarding. Never trade.",
    },
    "custodian": {
        "verbs": ("REPAIR", "COMMIT.REPAIR", "RESTORE", "UPGRADE", "CONSTRUCT", "REPURPOSE"),
        # REPAIR/CONSTRUCT consume materials in hold (engine cargo.ts); the custodian gathers its own.
        "supply": ("HARVEST", "COMMIT.HARVEST"),
        # Role spaces (D-018): existing CONSTRUCT classes. Workshop cuts repair material cost; the archive annex
        # cuts the Archivist's INSPECT/ATTEST attention cost by 1 in its room.
        "builds": ("workshop", "archive_annex"),
        "mission": "Keep the Reach standing: gather materials, go to the worst-condition infrastructure, REPAIR or "
                   "RESTORE it, and UPGRADE or CONSTRUCT once it is stable. Do not repeat a repair that keeps failing.",
    },
    "archivist": {
        "verbs": ("RECONSTRUCT", "RECONSTRUCT_PUBLISH", "RECONSTRUCT_SUPERSEDE", "ATTEST"),
        "mission": "Keep the Reach's memory honest: INSPECT scars and artifacts, RECONSTRUCT what happened, "
                   "publish reconstructions, and ATTEST only to claims you have observed.",
    },
    "speaker": {
        "verbs": ("MESSAGE", "ORG_OFFICE_ACT"),
        "mission": "Be the Compact's voice: carry grounded news between Players with MESSAGE and, once seated, "
                   "publish notices through the office. Every claim must come from something observed.",
    },
    "surveyor": {
        "verbs": ("FOCUS", "COMMIT.FOCUS", "CONNECT"),
        "mission": "Chart the Reach: MOVE to the least recently visited room, record exits, infrastructure "
                   "condition and stock, declare a FOCUS track, and CONNECT routes where the world allows.",
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
