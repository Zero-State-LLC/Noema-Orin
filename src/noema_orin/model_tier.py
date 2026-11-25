"""Per-turn decide-model tier by what the menu offers (D-030).

Verdicts come from `jev route-to` (cheap = routine, reversible, costs one turn if wrong;
strong = social, org or construction, hard to undo). Frozen here so the Orin needs no Jev
call per turn. Picks below 0.7 confidence were sent to strong. Regenerate with
scripts/jev_tier.sh when roles gain verbs.
"""

CHEAP = frozenset({
    "LOOK", "INSPECT", "WAIT", "OBSERVE", "MOVE", "ENTER_WORLD", "LEAVE_WORLD",
    "HARVEST", "COMMIT.HARVEST", "REPAIR", "COMMIT.REPAIR", "FOCUS", "COMMIT.FOCUS", "RESTORE",
})


def tier_for(options: list[dict]) -> str:
    """strong when any offered option is outside the cheap set, else cheap."""
    acts = {str(o.get("action") or "").upper() for o in options}
    return "cheap" if acts and acts <= CHEAP else "strong"
