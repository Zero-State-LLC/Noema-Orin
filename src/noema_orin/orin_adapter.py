"""Orin decision adapter: local Ollama with bounded latency, scripted fallback (D-009).

Wraps noema-client adapters. On model timeout or unusable output, falls back to the
client's FirstValidAffordanceAdapter so a member never stalls a cycle. Every proposal
still passes the client's own validate_proposal and the role policy.
"""

import json
import os
import urllib.request


class OrinAdapter:
    def __init__(self, *, base_url: str, model: str, brief: str, timeout: float = 120.0, num_ctx: int = 4096) -> None:
        from noema_client.adapters.openai_compatible import SYSTEM_PROMPT
        from noema_client.adapters.scripted import FirstValidAffordanceAdapter

        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.num_ctx = num_ctx
        self.system = SYSTEM_PROMPT + " Role: " + brief
        self.fallback = FirstValidAffordanceAdapter()
        self.stats = {"model": 0, "planner": 0, "fallback": 0, "loop_break": 0}
        self.recent: list[dict] = []
        self.allowed: frozenset = frozenset()
        self.default_args: dict[str, dict] = {}
        self.verbs: set[str] = set()
        self.supply: set[str] = set()
        from .health import RoleHealthTracker, WorkersAICircuitBreaker

        self.breaker = WorkersAICircuitBreaker()
        self.health = RoleHealthTracker(role="")
        self._last_remote = False
        self.builds: tuple = ()
        self.cohort_ids: set[str] = set()
        self.explorer = False
        self.memory = None
        self.world_map = None
        self.memories: list[dict] = []
        self.stats_mem = 0
        self.dwell = 0
        self.on_turn = None
        self.self_id = None
        self.role_handles: dict[str, str] = {}

    def set_brief(self, brief: str) -> None:
        from noema_client.adapters.openai_compatible import SYSTEM_PROMPT

        self.system = SYSTEM_PROMPT + " Role: " + brief

    def _chat(self, system: str, user: str, num_predict: int = 400) -> dict:
        """Cloud decision model when configured (D-016), local Ollama only as fallback.

        The circuit breaker skips Workers AI for its cooldown after repeated failures, so a
        cloud outage costs one 20s timeout per threshold, not one per turn.
        """
        import time

        now = time.time()
        cloud = None
        if self.breaker.allow_remote(now):
            cloud = _cloud_call("/chat", system, user, max_tokens=max(num_predict, 80), timeout=20)
            if cloud is not None:
                self.breaker.record_success()
            elif os.environ.get("MEMORY_SYNC_URL") and self.breaker.record_failure(now):
                print(json.dumps({"workers_ai": "circuit_open", "cooldown_s": self.breaker.cooldown_seconds}), flush=True)
        self._last_remote = cloud is not None
        if cloud is not None:
            self.stats_cloud = getattr(self, "stats_cloud", 0) + 1
            return cloud
        if os.environ.get("NOEMA_DECIDE_LOCAL_FALLBACK", "1") != "1":
            return {}
        payload = {"model": self.model, "stream": False, "format": "json",
                   "options": {"temperature": 0.4, "num_ctx": self.num_ctx, "num_predict": num_predict},
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        req = urllib.request.Request(self.base_url.removesuffix("/v1") + "/api/chat", data=json.dumps(payload).encode(),
                                     headers={"content-type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            text = (json.loads(resp.read().decode()).get("message") or {}).get("content") or "{}"
        data = json.loads(text[text.find("{"): text.rfind("}") + 1] or "{}")
        return data if isinstance(data, dict) else {}

    def _menu(self, context) -> list[dict]:
        from .planner import focus, refine

        canonical = context.get("canonical") or {}
        from .planner import prefer_builds

        menu = refine(_options(canonical, self.allowed), canonical, self.cohort_ids)
        if self.role_handles:
            from .offices import refine_offices, retarget_create
            from .planner import home_org

            home = home_org(canonical)
            menu = [m for m in (retarget_create(o, canonical, home) if o["action"] == "ORG_OFFICE_CREATE" else o
                                for o in menu) if m is not None]
            menu = refine_offices(menu, canonical, home, self.role_handles, self.role_handles.get("founder"))
        if self.builds:
            menu = prefer_builds(menu, self.builds, self._built_classes())
        if self.supply and _hold_ready(canonical):
            # Hold has enough materials for a build or repair: stop gathering, spend them.
            menu = [{**o, "i": i} for i, o in enumerate(o for o in menu if o["action"] not in self.supply)]
        return focus(menu, self.verbs)

    def _built_classes(self) -> set[str]:
        if self.memory is None:
            return set()
        rows = self.memory.db.execute("SELECT text FROM facts WHERE kind='built' AND stale=0").fetchall()
        return {t for (t,) in rows}

    def _ask(self, context, options):
        canonical = context.get("canonical") or {}
        recent = [f"{r['action']} {r.get('target') or ''}".strip() for r in self.recent[-5:]]
        if not options:
            return None
        menu = [{k: o[k] for k in ("i", "action", "label")} for o in options[:24]]
        loc = canonical.get("location") or {}
        user = json.dumps({"recent_own_actions": recent, "room": loc.get("name"), "memories": self.memories,
                           "resources": canonical.get("resources"), "options": menu}, sort_keys=True, default=str)[:5000]
        instruction = (self.system + " Choose exactly ONE option by its index from `options`. Prefer actions unique to your role "
                       "over LOOK, INSPECT and WAIT. Use `memories` (facts you observed earlier). "
                       "Vary your actions; never pick the same option three times in a row. "
                       "Reply ONLY with JSON {\"choice\": <index>, \"why\": \"<6 words>\"}. Do not echo the input.")
        data = self._chat(instruction, user, num_predict=60)
        idx = data.get("choice")
        if type(idx) is not int or not 0 <= idx < len(menu):
            return None
        return _proposal(options[idx], self.default_args, self.memory)

    def _loop_break_move(self, context):
        """MOVE needs a direction (bare MOVE is INVALID_PROPOSAL); take the least recently seen exit."""
        from noema_client.types import ActionProposal

        loc = (context.get("canonical") or {}).get("location") or {}
        allowed = getattr(self, "allowed", frozenset())
        if allowed and "MOVE" not in allowed:  # operator tier may not move (OPERATOR-MAINT-EVOLVE §1)
            return ActionProposal(action="WAIT")
        exits = {e.get("to_room_id"): e.get("direction") for e in loc.get("exits") or [] if isinstance(e, dict) and e.get("direction")}
        if not exits:
            return ActionProposal(action="WAIT")
        goal = self.world_map.least_recent(sorted(r for r in exits if r)) if self.world_map is not None else None
        return ActionProposal(action="MOVE", target_id=exits.get(goal) or sorted(exits.values())[0])

    def _role_fallback(self, context, options):
        """Scripted choice that still honours the role: unique verbs first, then MOVE, then anything allowed."""
        tried = {(r["action"], r.get("target")) for r in self.recent[-3:]}
        from .planner import SHARED

        for tier in (lambda o: o["action"] not in SHARED, lambda o: o["action"] == "MOVE", lambda o: True):
            for opt in options:
                if tier(opt) and (opt["action"], opt.get("target_id")) not in tried:
                    prop = _proposal(opt, self.default_args, self.memory)
                    if prop is not None:
                        return prop
        return self.fallback.decide(context)

    def _plan(self, context, options):
        """Remember what is observed, then route if this room offers none of the role's verbs."""
        from noema_client.types import ActionProposal

        from .planner import facts_from, has_role_verb, route

        canonical = context.get("canonical") or {}
        loc = canonical.get("location") or {}
        room = loc.get("room_id")
        seq = canonical.get("sequence")
        if self.world_map is not None and room:
            self.world_map.observe(room, loc.get("name"), seq, [e.get("to_room_id") for e in loc.get("exits") or [] if isinstance(e, dict)],
                                   [str(a.get("operation") or a.get("action") or "").upper() for a in canonical.get("affordances") or []
                                    if isinstance(a, dict) and a.get("available") is not False])
        if self.memory is not None:
            facts = facts_from(canonical)
            for kind, text in facts:
                self.memory.remember(text, kind=kind, room=room, sequence=seq)
            self.memory.mark_stale(kind="offer", room=room, keep={t for k, t in facts if k == "offer"})
            for ent in loc.get("entities") or canonical.get("entities") or []:
                cls = isinstance(ent, dict) and ent.get("entity_type") == "INFRASTRUCTURE" and (
                    ent.get("infra_type") or str(ent.get("label") or "").replace("-", "_"))
                if cls and not ent.get("in_progress"):
                    self.memory.remember(str(cls), kind="built", room=room, sequence=seq)
            self.memories = self.memory.recall(" ".join([str(loc.get("name") or "")] + sorted(self.verbs)))
            self.stats_mem += len(self.memories)
        goal_verbs = self.verbs
        if self.supply and _hold_empty(canonical):
            goal_verbs = self.supply  # gather materials before repair/construct (engine cargo rule)
        if _starved_for_attention(canonical, goal_verbs):
            self.dwell = 0
            return ActionProposal(action="WAIT")  # engine: WAIT restores attention +2 (cap 8)
        here = has_role_verb(options, goal_verbs)
        if self.builds and _hold_ready(canonical):
            pick = next((o for o in options if o["action"] == "CONSTRUCT"
                         and str((o.get("raw") or {}).get("class") or "") in self.builds), None)
            if pick is not None:
                return _proposal(pick, self.default_args, self.memory)  # build the role's own space (D-018)
        if self.world_map is None or here or self.dwell < 2 or (self.allowed and "MOVE" not in self.allowed):
            self.dwell = self.dwell + 1 if not here else 0
            return None
        if not _can_afford_move(canonical):
            return ActionProposal(action="WAIT")  # WAIT burns cargo for energy; a refused MOVE wastes a turn
        direction = route(canonical, self.world_map, goal_verbs, explorer=self.explorer)
        if not direction:
            return None
        self.dwell = 0
        return ActionProposal(action="MOVE", target_id=direction)

    def decide(self, context):
        self.self_id = (context.get("canonical") or {}).get("self") or getattr(self, "self_id", None)
        if self.on_turn is not None:
            self.cohort_ids = self.on_turn(self.self_id)
        options = self._menu(context)
        source = "model"
        try:
            proposal = self._plan(context, options)
        except Exception as exc:  # memory must never stall a turn
            print(json.dumps({"memory_error": type(exc).__name__}), flush=True)
            proposal = None
        if proposal is not None:
            source = "planner"
            self.stats["planner"] += 1
        else:
            try:
                proposal = self._ask(context, options)
            except Exception:
                proposal = None
        if source == "planner":
            pass
        elif proposal is not None:
            self.stats["model"] += 1
        else:
            source = "fallback"
            self.stats["fallback"] += 1
            proposal = self._role_fallback(context, options)
        key = (getattr(proposal, "action", None), getattr(proposal, "target_id", None))
        if len(self.recent) >= 2 and all((r["action"], r.get("target")) == key for r in self.recent[-2:]):
            from noema_client.types import ActionProposal

            source = "loop_break"
            self.stats["loop_break"] += 1
            proposal = self._loop_break_move(context) if key[0] != "MOVE" else ActionProposal(action="LOOK")
        self.recent = (self.recent + [{"action": getattr(proposal, "action", None),
                                       "target": getattr(proposal, "target_id", None)}])[-40:]
        canonical = (context.get("canonical") or {})
        self.health.record_turn(verb=str(getattr(proposal, "action", "") or ""),
                                used_workers_ai=bool(getattr(self, "_last_remote", False)) or source == "planner",
                                source_sequence=int(canonical.get("sequence") or 0))
        self._last_remote = False
        print(json.dumps({"turn": sum(self.stats.values()), "source": source,
                          "action": getattr(proposal, "action", None),
                          "memories_used": len(self.memories)}), flush=True)
        return proposal


def _starved_for_attention(canonical: dict, verbs: set[str]) -> bool:
    """A role verb is offered here but unaffordable for lack of a budget WAIT restores.

    Engine: WAIT restores attention (+2, cap 8) and burns 1 cargo for +2 energy (cargo.ts applyCargoFuel).
    """
    res = canonical.get("resources") or {}
    for aff in canonical.get("affordances") or []:
        if not isinstance(aff, dict) or aff.get("available") is not False:
            continue
        op = str(aff.get("operation") or aff.get("action") or "").upper()
        if op not in verbs:
            continue
        reason = str(aff.get("reason") or "")
        for budget in ("attention", "energy"):
            need = (aff.get("requires") or {}).get(budget)
            have = res.get(budget)
            if isinstance(need, (int, float)) and isinstance(have, (int, float)) and have < need and budget in reason:
                return True
    return False


def _can_afford_move(canonical: dict) -> bool:
    """Engine transport.ts: MOVE costs 1 energy, +1 while carrying anything (storage < 16)."""
    res = canonical.get("resources") or {}
    energy, storage = res.get("energy"), res.get("storage")
    if not isinstance(energy, (int, float)):
        return True
    cost = 1 + (1 if isinstance(storage, (int, float)) and storage < 16 else 0)
    return energy >= cost


def _hold_ready(canonical: dict, need: int = 6) -> bool:
    """Engine hold = 16 - free storage; most builds take 4-6 storage, repair takes 1."""
    storage = (canonical.get("resources") or {}).get("storage")
    return isinstance(storage, (int, float)) and 16 - storage >= need


def _hold_empty(canonical: dict) -> bool:
    """Engine: hold occupied = STORAGE_CAPACITY(16) - free storage. Empty hold blocks REPAIR/CONSTRUCT."""
    storage = (canonical.get("resources") or {}).get("storage")
    return isinstance(storage, (int, float)) and storage >= 16


def _options(canonical: dict, allowed: frozenset) -> list[dict]:
    """Available advertised affordances this role may use, as a short indexed menu.

    `action` is the operation the server executes (ORG_INVITE -> ORG_MEMBER_ADD) and
    `raw` is kept so the proposal is built by the client's own affordance mapper.
    """
    out = []
    for aff in canonical.get("affordances") or []:
        if not isinstance(aff, dict) or aff.get("available") is False:
            continue
        shown = str(aff.get("action") or aff.get("verb") or "").upper()
        op = str(aff.get("operation") or shown).upper()
        if allowed and op not in allowed and shown not in allowed:
            continue
        out.append({"i": len(out), "action": shown if shown in allowed else op, "label": str(aff.get("label") or "")[:60],
                    "target_id": aff.get("target_id") or aff.get("target"), "target_label": aff.get("target_label"),
                    "arguments": {k: aff[k] for k in ("org_id",) if k in aff}, "raw": aff})
        if len(out) >= 40:
            break
    return out


def _proposal(opt: dict, default_args: dict, memory=None):
    from noema_client.affordances import proposal_from_affordance
    from noema_client.types import ActionProposal

    base = proposal_from_affordance(opt["raw"]) if opt.get("raw") else None
    if base is None:
        return ActionProposal(action=opt["action"], target_id=opt.get("target_id"), arguments=dict(default_args.get(opt["action"], {})))
    args = {**default_args.get(base.action, {}), **_cmd_args(opt["raw"]), **dict(base.arguments or {})}
    if base.action == "ORG_OFFICE_ACT" and not args.get("notice") and not args.get("governance_rule"):
        notice = grounded_notice(memory)
        if not notice:
            return None  # nothing observed worth publishing; never post filler (S13)
        args["notice"] = notice
    return ActionProposal(action=base.action, target_id=base.target_id, arguments=args)


def _cmd_args(raw: dict) -> dict:
    """Ids and fields some LOOK affordances only carry in target_id/target_label/cmd.

    The server wants org_id / office_id / agent_id plus profile/display_name/role, while
    LOOK may only show them as `target_id`, `target_label` and `name=`/`profile=`/`role=` in cmd.
    """
    import shlex

    op = str(raw.get("operation") or raw.get("action") or "").upper()
    if not op.startswith("ORG_"):
        return {}
    try:
        parts = shlex.split(str(raw.get("cmd") or ""))
    except ValueError:
        parts = []
    kv = dict(p.split("=", 1) for p in parts if "=" in p)
    out: dict = {}
    for ref in [raw.get("target_id")] + parts:
        ref = str(ref or "")
        if ref.startswith("org.") and "org_id" not in out:
            out["org_id"] = ref
        elif ref.startswith("office.") and "office_id" not in out:
            out["office_id"] = ref
            out.setdefault("org_id", "org." + ref.split(".")[1] + "." + ref.split(".")[2] if ref.count(".") >= 3 else None)
    label = raw.get("player_id") or raw.get("agent_id") or raw.get("target_label")
    if label and op in AGENT_OPS:
        out["agent_id"] = label if str(label).startswith("player.") else f"player.{label}"
    if "name" in kv:
        out["display_name"] = kv["name"]
    for key in ("profile", "role"):
        if key in kv:
            out[key] = kv[key]
    return {k: v for k, v in out.items() if v}


def grounded_notice(memory, org_name: str = "the Compact") -> str | None:
    """A public notice built only from observed, non-stale facts, citing the source sequence (S13)."""
    if memory is None:
        return None
    row = memory.db.execute(
        "SELECT text, source_sequence FROM facts WHERE stale=0 AND kind IN ('consequence','room') "
        "AND text NOT LIKE 'You take in%' AND text NOT LIKE 'You arrive%' AND text NOT LIKE 'Enter the world%' "
        "ORDER BY sequence DESC LIMIT 1").fetchone()
    if not row:
        return None
    text, seq = row
    return f"{org_name} notice: {text} (observed at seq {seq})"[:280]


AGENT_OPS = {"ORG_MEMBER_ADD", "ORG_OFFICE_ASSIGN", "ORG_SUCCESSION_DESIGNATE", "ORG_SUCCESSION_CONSENT"}


def _compact(canonical):
    """Keep only decision-relevant LOOK fields so a 3B model fits its window."""
    keep = ("room", "room_id", "room_name", "affordances", "available_actions", "exits", "entities", "resources", "cargo", "budget", "energy", "world_status")
    out = {k: canonical[k] for k in keep if k in canonical}
    return out or canonical


def reflect(adapter: OrinAdapter, persona: dict, recent: list[dict]) -> object:
    """Ask the model for a bounded persona patch from this session's own actions."""
    system = ("You reflect on a game character's last session and propose small changes to temperament. "
              "Reply only with JSON {\"trait_deltas\": {trait: number between -0.1 and 0.1}, "
              "\"lesson\": one short sentence learned, \"quirk\": optional new quirk}. Traits: caution, curiosity, "
              "sociability, thrift. Do not change name or role.")
    user = json.dumps({"persona": {k: persona[k] for k in ("name", "role", "traits", "quirk", "lessons")},
                       "session_actions": recent[-40:]})[:6000]
    cloud = _cloud_reflect(system, user)
    if cloud is not None:
        return cloud
    if os.environ.get("NOEMA_REFLECT_LOCAL_FALLBACK", "0") != "1":
        return None  # skip this session's drift rather than load the Orin's model (D-015)
    try:
        return adapter._chat(system, user, num_predict=200)
    except Exception:
        return None


def _cloud_reflect(system: str, user: str) -> dict | None:
    """Reflection on Workers AI via the private memory Worker (D-015). None when unset or unreachable."""
    return _cloud_call("/reflect", system, user, timeout=60)


def _cloud_call(path: str, system: str, user: str, *, max_tokens: int | None = None, timeout: float = 60) -> dict | None:
    """POST to the private Worker; parse the first JSON object from the model text."""
    url, token = os.environ.get("MEMORY_SYNC_URL"), os.environ.get("MEMORY_SYNC_TOKEN")
    if not url or not token:
        return None
    body = {"system": system, "user": user}
    if max_tokens:
        body["max_tokens"] = max_tokens
    req = urllib.request.Request(url.rstrip("/") + path, method="POST",
                                 data=json.dumps(body).encode(),
                                 headers={"authorization": f"Bearer {token}", "content-type": "application/json",
                                          "user-agent": "noema-orin/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = str(json.loads(resp.read().decode()).get("text") or "")
    except Exception:
        return None
    try:
        data = json.loads(text[text.find("{"): text.rfind("}") + 1] or "{}")
    except ValueError:
        return None
    return data if isinstance(data, dict) and data else None


def from_env(brief: str) -> OrinAdapter:
    return OrinAdapter(base_url=os.environ.get("NOEMA_LLM_BASE", "http://127.0.0.1:11434/v1"),
                       model=os.environ.get("NOEMA_LLM_MODEL", "qwen2.5:3b"), brief=brief)
