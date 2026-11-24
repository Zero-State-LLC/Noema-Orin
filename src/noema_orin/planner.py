"""Deterministic planning layer in front of the small model (issue #31, T17/T18).

Pure functions over the client's canonical context and the shared map. The planner
narrows the option menu (no duplicate orgs, one home org, cohort first) and, when the
current room offers none of the role's own verbs, routes toward a room that does.
"""

SHARED = {"LOOK", "INSPECT", "WAIT", "OBSERVE", "ENTER_WORLD", "LEAVE_WORLD", "MOVE"}
ORG_VERBS = {"ORG_INVITE", "ORG_MEMBER_ADD", "ORG_OFFICE_CREATE", "ORG_OFFICE_ASSIGN", "ORG_OFFICE_VACATE",
             "ORG_SUCCESSION_RULE", "ORG_SUCCESSION_DESIGNATE", "ORG_OFFICE_ACT"}
# Trade and access stay out of role agents' reach (DENY_ALWAYS); agreements of those types are filtered too.
BLOCKED_AGREEMENTS = {"trade", "access"}


def home_org(canonical: dict) -> str | None:
    """The oldest org this Player founded; every later org act targets it."""
    mine = [o for o in canonical.get("organizations") or [] if isinstance(o, dict) and o.get("my_role") == "founder"]
    if not mine:
        return None
    return min(mine, key=lambda o: (o.get("created_cycle") or 0, o.get("org_id") or ""))["org_id"]


def _org_of(opt: dict) -> str | None:
    args = opt.get("arguments") or {}
    for v in (args.get("org_id"), opt.get("target_id")):
        if isinstance(v, str) and v.startswith("org."):
            return v
    return None


def _office_named(canonical: dict, home: str, opt: dict) -> bool:
    """True when the home org already has an office of the name this option would create."""
    import re

    m = re.search(r'name="?([^"]+)"?', str((opt.get("raw") or {}).get("cmd") or ""))
    if not m:
        return False
    for org in canonical.get("organizations") or []:
        if isinstance(org, dict) and org.get("org_id") == home:
            return any(o.get("display_name") == m.group(1) for o in org.get("offices") or [] if isinstance(o, dict))
    return False


def refine(options: list[dict], canonical: dict, cohort_ids: set[str]) -> list[dict]:
    """Drop duplicate org creation and acts on non-home orgs; put cohort invites first."""
    home = home_org(canonical)
    members = set()
    for org in canonical.get("organizations") or []:
        if isinstance(org, dict) and org.get("org_id") == home:
            members = {m.get("agent_id") for m in org.get("members") or [] if isinstance(m, dict)}
    handles = {p.get("handle"): p.get("player_id") for p in canonical.get("players_here") or [] if isinstance(p, dict)}
    out, invites = [], []
    for opt in options:
        action = opt["action"]
        if action == "ORG_CREATE" and home:
            continue
        if action == "ORG_OFFICE_CREATE" and home and _office_named(canonical, home, opt):
            continue
        if action in ORG_VERBS and home and _org_of(opt) not in (None, home):
            continue
        if action in ("ORG_INVITE", "ORG_MEMBER_ADD"):
            pid = handles.get(opt.get("target_label"))
            if pid not in cohort_ids or pid in members:
                continue
            invites.append(opt)
            continue
        if action == "AGREEMENT_FORM":
            raw = opt.get("raw") or {}
            if str(raw.get("agreement_type") or "").lower() in BLOCKED_AGREEMENTS or (raw.get("player_id") or opt.get("target_id")) not in cohort_ids:
                continue
        out.append(opt)
    merged = invites + out
    if not home and any(o["action"] == "ORG_CREATE" for o in merged):
        # Founding comes first: until a home org exists, the only org act is creating it.
        merged = [o for o in merged if o["action"] == "ORG_CREATE"][:1]
    return [{**o, "i": i} for i, o in enumerate(merged)]


def has_role_verb(options: list[dict], verbs: set[str]) -> bool:
    return any(o["action"] in verbs for o in options)


IDLE = {"LOOK", "INSPECT", "WAIT", "OBSERVE"}


def prefer_builds(options: list[dict], builds: tuple, built: set[str]) -> list[dict]:
    """Role spaces first: CONSTRUCT of a class this role builds and nobody has built yet; drop other CONSTRUCTs."""
    if not builds:
        return options
    want = [b for b in builds if b not in built]
    first, rest = [], []
    for o in options:
        cls = str((o.get("raw") or {}).get("class") or "")
        if o["action"] == "CONSTRUCT":
            if cls in want:
                first.append((want.index(cls), o))
            continue
        rest.append(o)
    ordered = [o for _, o in sorted(first, key=lambda t: t[0])] + rest
    return [{**o, "i": i} for i, o in enumerate(ordered)]


def focus(options: list[dict], verbs: set[str]) -> list[dict]:
    """When the role's own verbs are on offer, hide idle perception so the model acts in role."""
    if not has_role_verb(options, verbs):
        return options
    kept = [o for o in options if o["action"] not in IDLE]
    return [{**o, "i": i} for i, o in enumerate(kept)]


def route(canonical: dict, world_map, verbs: set[str], *, explorer: bool) -> str | None:
    """Exit direction to take, or None to decide in place."""
    loc = canonical.get("location") or {}
    here = loc.get("room_id")
    exits = {e.get("to_room_id"): e.get("direction") for e in loc.get("exits") or [] if isinstance(e, dict)}
    if not here or not exits:
        return None
    if explorer:
        goal = world_map.least_recent(sorted(r for r in exits if r))
        return exits.get(goal)
    goal = world_map.where_offered(verbs, exclude=here)
    if goal is None:
        goal = world_map.least_recent(sorted(r for r in exits if r))
        return exits.get(goal)
    hop = world_map.next_hop(here, goal)
    return exits.get(hop) if hop else None


def facts_from(canonical: dict) -> list[tuple[str, str]]:
    """(kind, text) facts worth remembering from one observation. Observed only, no inference."""
    loc = canonical.get("location") or {}
    name = loc.get("name") or loc.get("room_id") or "?"
    out = []
    if loc.get("condition"):
        out.append(("room", f"{name}: {loc['condition']}"))
    acts = sorted({str(a.get("action") or "").upper() for a in canonical.get("affordances") or []
                   if isinstance(a, dict) and a.get("available") is not False} - SHARED - {""})
    if acts:
        out.append(("offer", f"{name} offers {' '.join(acts)}"))
    cons = canonical.get("last_consequence")
    if cons:
        out.append(("consequence", str(cons)[:240]))
    return out
