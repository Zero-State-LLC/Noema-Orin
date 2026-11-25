"""Office catalog for the Reach Compact (S10-S12, S14). Pure functions, no I/O.

Each role maps to at most one named office whose engine authority profile matches
the role's charter (engine offices.ts OFFICE_PROFILES). Roles whose only fitting
profile is TRADE or ACCESS authority get no seat, because role agents keep those
verbs off (roles.DENY_ALWAYS).
"""

CATALOG: dict[str, tuple[str, str]] = {
    "speaker": ("Notice", "PUBLISH_NOTICE"),
    "custodian": ("Steward", "OPERATE_NAMED_ASSET"),  # engine: repair local infra for the org, VEST
    "archivist": ("Archive Keeper", "ACCESS_RESTRICTED_ARCHIVE"),
    # D-047 (RFC-0133): the seat unlocks treasury HARVEST and SUPPLY. The profile also carries treasury TRADE,
    # which the agent never sends (roles.DENY_ALWAYS blocks TRADE in the client policy).
    "quartermaster": ("Quartermaster", "OPERATE_RESOURCE_ACCOUNT"),
}
# Not seated: surveyor (GRANT_ACCESS).


def _home(canonical: dict, home: str | None) -> dict:
    for org in canonical.get("organizations") or []:
        if isinstance(org, dict) and org.get("org_id") == home:
            return org
    return {}


def live_offices(canonical: dict, home: str | None) -> list[dict]:
    return [o for o in _home(canonical, home).get("offices") or []
            if isinstance(o, dict) and o.get("status") != "RETIRED"]


def missing(canonical: dict, home: str | None) -> list[tuple[str, str]]:
    """Catalog offices the home org lacks, in catalog order."""
    have = {o.get("display_name") for o in live_offices(canonical, home)}
    return [spec for spec in CATALOG.values() if spec[0] not in have]


def duplicates(canonical: dict, home: str | None) -> set[str]:
    """Office ids to retire: all but one office per display name. Keep the occupied one, else the oldest id."""
    by_name: dict[str, list[dict]] = {}
    for o in live_offices(canonical, home):
        by_name.setdefault(str(o.get("display_name")), []).append(o)
    out: set[str] = set()
    for group in by_name.values():
        if len(group) < 2:
            continue
        keep = sorted(group, key=lambda o: (o.get("status") != "OCCUPIED", str(o.get("office_id"))))[0]
        out |= {str(o.get("office_id")) for o in group if o is not keep}
    return out


def intended_holder(office: dict, role_handles: dict[str, str]) -> str | None:
    for role, (name, _profile) in CATALOG.items():
        if office.get("display_name") == name:
            return role_handles.get(role)
    return None


def create_args(home: str, spec: tuple[str, str]) -> dict:
    name, profile = spec
    return {"operation": "ORG_OFFICE_CREATE", "org_id": home, "display_name": name, "profile": profile}


def retarget_create(opt: dict, canonical: dict, home: str | None) -> dict | None:
    """The engine only advertises a Notice create, but its parser takes any profile. Point it at the next
    missing catalog office, or drop it when the catalog is complete."""
    if not home:
        return opt
    todo = missing(canonical, home)
    if not todo:
        return None
    name, profile = todo[0]
    raw = {**(opt.get("raw") or {}), "cmd": f'office create {home} name="{name}" profile={profile}', "target_id": home}
    return {**opt, "raw": raw, "target_id": home, "label": f"Create {name} office"}


def refine_offices(options: list[dict], canonical: dict, home: str | None, role_handles: dict[str, str],
                   founder_handle: str | None) -> list[dict]:
    """Keep only office acts that move the catalog forward.

    ASSIGN: only the catalog's intended holder. RETIRE: only duplicates. SUCCESSION_DESIGNATE: a cohort heir other
    than the holder, only while no successor is named. SUCCESSION_RULE: only while no successor is named.
    """
    if not home:
        return options
    offices = {str(o.get("office_id")): o for o in live_offices(canonical, home)}
    dupes = duplicates(canonical, home)
    out = []
    for opt in options:
        action = opt["action"]
        oid = str(opt.get("target_id") or (opt.get("raw") or {}).get("office_id") or "")
        office = offices.get(oid)
        if action == "ORG_OFFICE_ASSIGN":
            if office is None or oid in dupes or opt.get("target_label") != intended_holder(office, role_handles):
                continue
        elif action == "ORG_OFFICE_RETIRE":
            if oid not in dupes:
                continue
        elif action == "ORG_SUCCESSION_DESIGNATE":
            raw = opt.get("raw") or {}
            heir = str(raw.get("player_id") or "").replace("player.", "", 1)
            if (office is None or office.get("successor_handle") or oid in dupes
                    or heir not in set(role_handles.values()) or heir == office.get("holder_handle")):
                continue
        elif action == "ORG_SUCCESSION_RULE":
            # Engine: publishing a rule unsets `successors`, so RULE and DESIGNATE undo each other.
            # Prefer naming a cohort heir; publish member_order only when no heir can be designated here.
            heirs = {str((o.get("raw") or {}).get("player_id") or "").replace("player.", "", 1) for o in options
                     if o["action"] == "ORG_SUCCESSION_DESIGNATE" and o.get("target_id") == oid}
            if office is None or office.get("successor_handle") or oid in dupes or heirs & set(role_handles.values()):
                continue
        out.append(opt)
    return [{**o, "i": i} for i, o in enumerate(out)]
