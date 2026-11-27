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


PINNED_HOME: str | None = None  # set from shared/home_org; survives observations that omit organizations


def home_org(canonical: dict) -> str | None:
    """The pinned home org, else the oldest org this Player founded; every later org act targets it."""
    if PINNED_HOME:
        return PINNED_HOME
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
    here_player_ids = {str(p.get("player_id") or "") for p in canonical.get("players_here") or [] if isinstance(p, dict)}
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
            party = str(raw.get("player_id") or opt.get("target_id") or "")
            if str(raw.get("agreement_type") or "").lower() in BLOCKED_AGREEMENTS:
                continue
            # T5/#159 (D-076): enforce colocation to eliminate NOT_COLOCATED rejections; allow colocated external diplomacy.
            if "players_here" in canonical and party not in here_player_ids:
                continue
            if "players_here" not in canonical and party not in cohort_ids:
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


def focus(
    options: list[dict],
    verbs: set[str],
    held_track: str | None = None,
    *,
    held_tracks: list[str] | tuple[str, ...] | None = None,
    desired_tracks: tuple[str, ...] | list[str] | None = None,
) -> list[dict]:
    """When the role's own verbs are on offer, hide idle perception so the model acts in role."""
    options = _drop_held_focus(options, held_track, held_tracks=held_tracks, desired_tracks=desired_tracks)
    if not has_role_verb(options, verbs):
        return options
    kept = [o for o in options if o["action"] not in IDLE]
    return [{**o, "i": i} for i, o in enumerate(kept)]


def _focus_track_of(opt: dict) -> str:
    raw = opt.get("raw") or {}
    track = raw.get("track") or (opt.get("arguments") or {}).get("track")
    if track:
        return str(track).strip().lower()
    cmd = str(raw.get("cmd") or "").strip().lower().split()
    if len(cmd) >= 2 and cmd[0] == "focus":
        return cmd[1].strip("\"'")
    tgt = str(opt.get("target_id") or "").strip().lower()
    if tgt and not tgt.startswith(("entity.", "room.", "player.", "org.")):
        return tgt
    return ""


def _drop_held_focus(
    options: list[dict],
    held_track: str | None = None,
    *,
    held_tracks: list[str] | tuple[str, ...] | None = None,
    desired_tracks: tuple[str, ...] | list[str] | None = None,
) -> list[dict]:
    """D-049 + RFC-0144 §1 (ACTIVE_FOCUS_CAP = 2): allow missing desired tracks; drop held/unwanted FOCUS."""
    held = [str(t).strip().lower() for t in (held_tracks or ()) if str(t or "").strip()]
    if not held and held_track:
        held = [str(held_track).strip().lower()]
    desired = [str(t).strip().lower() for t in (desired_tracks or ()) if str(t or "").strip()]
    if desired:
        missing = [t for t in desired if t not in held]
        if not missing:
            kept = [o for o in options if o["action"] not in ("FOCUS", "COMMIT.FOCUS")]
        else:
            kept = [
                o for o in options
                if o["action"] not in ("FOCUS", "COMMIT.FOCUS") or _focus_track_of(o) in missing
            ]
        return [{**o, "i": i} for i, o in enumerate(kept)] if len(kept) != len(options) else options
    if not held:
        return options
    # Legacy single-track guard when caller specifies no desired_tracks.
    kept = [o for o in options if o["action"] not in ("FOCUS", "COMMIT.FOCUS")]
    return [{**o, "i": i} for i, o in enumerate(kept)] if len(kept) != len(options) else options


def route(
    canonical: dict,
    world_map,
    verbs: set[str],
    *,
    explorer: bool,
    me: str | None = None,
    avoid_pressure: bool = False,
    pressure_weight: float = 0.7,
    seek_scars: bool = False,
    current_seq: int | None = None,
) -> str | None:
    """Exit direction to take, or None to decide in place."""
    loc = canonical.get("location") or {}
    here = loc.get("room_id")
    exits = {e.get("to_room_id"): e.get("direction") for e in loc.get("exits") or [] if isinstance(e, dict)}
    if not here or not exits:
        return None
    if explorer:
        goal = world_map.least_recent(sorted(r for r in exits if r))
        return exits.get(goal)
    goal = None
    if seek_scars and hasattr(world_map, "scarred_rooms"):
        scarred = world_map.scarred_rooms(exclude=here, near=here)
        if scarred:
            goal = scarred[0]
    if goal is None and me and hasattr(world_map, "work_for"):
        # S10: rooms where this agent itself saw role work (its own work queue), nearest first.
        rooms = {r for r, a, _t, _n in world_map.work_for(me) if a in verbs and r != here}
        dist = world_map.distances(here) if rooms else {}
        reach = sorted((dist[r], r) for r in rooms if r in dist)
        goal = reach[0][1] if reach else None
    if goal is None and hasattr(world_map, "shared_work"):
        # T2/#156: consume cross-cohort damaged infra & scars discovered by surveyor/peers, skipping claimed targets.
        seq_now = current_seq if current_seq is not None else canonical.get("sequence")
        claimed = (
            set(world_map.active_claims(int(seq_now), exclude_member=me))
            if seq_now is not None and hasattr(world_map, "active_claims")
            else set()
        )
        shared = world_map.shared_work(verbs, exclude_targets=claimed, exclude_room=here)
        if shared:
            dist = world_map.distances(here)
            reach = sorted(
                (dist[row["room_id"]], int(row.get("condition") if row.get("condition") is not None else 100), row["room_id"])
                for row in shared
                if row["room_id"] in dist
            )
            goal = reach[0][2] if reach else None
    if goal is None and avoid_pressure and hasattr(world_map, "low_pressure_offered"):
        goal = world_map.low_pressure_offered(verbs, exclude=here, near=here, pressure_weight=pressure_weight)
    if goal is None:
        goal = world_map.where_offered(verbs, exclude=here, near=here)
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
    for scar in canonical.get("scars") or []:
        if isinstance(scar, dict) and scar.get("scar_id"):
            dom = scar.get("domain") or "economic"
            strength = round(float(scar.get("strength") or 0.0), 2)
            out.append(("scar", f"{name} bears a {dom} scar (strength {strength})"))
    for lore in canonical.get("lore_attractors") or []:
        if isinstance(lore, dict) and lore.get("label"):
            basin = lore.get("basin") or "forming"
            out.append(("lore", f"{name} lore attractor ({basin}): {lore['label']}"))
    for line in canonical.get("culture_lines") or []:
        if str(line or "").strip():
            out.append(("culture", f"{name}: {str(line).strip()}"))
    for line in canonical.get("inherited_lines") or []:
        if str(line or "").strip():
            out.append(("inherited", str(line).strip()))
    for line in canonical.get("rumor_lines") or []:
        if str(line or "").strip():
            out.append(("rumor", str(line).strip()))
    norms = canonical.get("active_norms") if isinstance(canonical.get("active_norms"), dict) else {}
    if float(norms.get("harvest_pressure") or 0) >= 2:
        out.append(("pressure", f"{name} harvest pressure {norms['harvest_pressure']}"))
    return out
