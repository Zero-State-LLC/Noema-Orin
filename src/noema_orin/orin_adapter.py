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
        self.focus_tracks: tuple[str, ...] = ()
        self.held_tracks: list[str] = []
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
        self.policy_knobs: dict[str, float | int] = {}
        self.persona_traits: dict[str, float] = {}
        self.mind_dir = None
        self.turn_log: list[dict] = []
        self.deep_time_seen: dict[str, int] = {"scars": 0, "lore": 0, "culture": 0, "inherited": 0}
        self._attested_targets: set[str] = set()
        self._last_social_turn: int = -999
        self.last_cycle: int | None = None
        self.last_playbook_state: str | None = None
        self.agenda_manager = None
        self.transition_log = None
        self.consequence_model = None
        self.consequence_scorer = None

    def _shadow_consequence(self, canonical: dict, proposal):
        """C3 (#198): shadow-mode estimate for the chosen action. Read-only: it never alters the proposal,
        and a failure here must never stall a turn. None when shadow mode is off."""
        model = getattr(self, "consequence_model", None)
        if model is None:
            return None
        try:
            from .consequence import compact

            prediction = model.predict(canonical, proposal)
            scorer = getattr(self, "consequence_scorer", None)
            if scorer is not None:
                scorer.note(canonical, proposal, prediction)
            return compact(prediction)
        except Exception as exc:
            print(json.dumps({"consequence_error": type(exc).__name__}), flush=True)
            return None

    def _effective_social_cooldown(self) -> int:
        knobs = getattr(self, "policy_knobs", None) or {}
        traits = getattr(self, "persona_traits", None) or {}
        base = int(knobs.get("social_outreach_cooldown", 12))
        soc = max(0.0, min(1.0, float(traits.get("sociability", 0.5))))
        return max(4, min(36, int(round(base * (1.2 - 0.4 * soc)))))

    def _social_outreach_ready(self, current_turn: int | None = None) -> bool:
        turn_n = sum((getattr(self, "stats", None) or {}).values()) if current_turn is None else int(current_turn)
        last = int(getattr(self, "_last_social_turn", -999))
        return (turn_n - last) >= self._effective_social_cooldown()

    def _effective_energy_floor(self) -> int:
        knobs = getattr(self, "policy_knobs", None) or {}
        traits = getattr(self, "persona_traits", None) or {}
        base = int(knobs.get("energy_reserve_floor", 3))
        caution = float(traits.get("caution", 0.5))
        return max(1, min(6, base + (1 if caution >= 0.75 else 0)))

    def _effective_dwell_limit(self) -> int:
        knobs = getattr(self, "policy_knobs", None) or {}
        traits = getattr(self, "persona_traits", None) or {}
        base = int(knobs.get("dwell_before_route", 2))
        curiosity = float(traits.get("curiosity", 0.5))
        return max(1, min(4, base - (1 if curiosity >= 0.75 else 0)))

    def _effective_treasury_floor(self) -> int:
        traits = getattr(self, "persona_traits", None) or {}
        thrift = max(0.0, min(1.0, float(traits.get("thrift", 0.5))))
        return TREASURY_BUILD_FLOOR + int(round(max(0.0, thrift - 0.5) * 8))

    def _inspect_novelty_window(self) -> int:
        knobs = getattr(self, "policy_knobs", None) or {}
        traits = getattr(self, "persona_traits", None) or {}
        w = max(0.0, min(1.0, float(knobs.get("inspect_novelty_weight", 0.6))))
        curiosity = max(0.0, min(1.0, float(traits.get("curiosity", 0.5))))
        return max(6, min(30, int(round(8 + (w * 0.7 + curiosity * 0.3) * 18))))

    def set_brief(self, brief: str) -> None:
        from noema_client.adapters.openai_compatible import SYSTEM_PROMPT

        self.system = SYSTEM_PROMPT + " Role: " + brief

    def _chat(
        self,
        system: str,
        user: str,
        num_predict: int = 400,
        tier: str | None = None,
        *,
        response_format: dict | None = None,
    ) -> dict:
        """System-1 local Orin GPU (`NOEMA_INFERENCE_MODE=local_first`) or Workers AI primary (`cloud_first`).

        In `local_first` mode (T10/#164), routine choices run locally on `llama-server` with constrained
        JSON-schema decoding (`$0` marginal cost); Workers AI acts as System-2 escalation/failover.
        """
        import time

        from .llm_client import call_llama_server

        mode = os.environ.get("NOEMA_INFERENCE_MODE", "cloud_first").strip().lower()
        now = time.time()
        self._last_local_s1 = False
        self._last_local = False

        if mode == "local_first" and tier != "escalate":
            local_url = os.environ.get("NOEMA_LOCAL_LLM_BASE", self.base_url)
            local_model = os.environ.get("NOEMA_LOCAL_LLM_MODEL", self.model)
            local_out = call_llama_server(
                base_url=local_url,
                model=local_model,
                system=system,
                user=user,
                response_format=response_format,
                max_tokens=max(num_predict, 60),
                timeout=min(self.timeout, 15.0),
            )
            if local_out is not None:
                self._last_remote = False
                self._last_local_s1 = True
                return local_out

        cloud = None
        if self.breaker.allow_remote(now):
            cloud = _cloud_call("/chat", system, user, max_tokens=max(num_predict, 80), timeout=20, tier=tier)
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
        # D-090: the last resort is llama-server's OpenAI route, with or without a JSON schema. The Ollama
        # /api/chat path is gone (llama-server answers it 404, and Ollama is retired on the Orin).
        llama_fb = call_llama_server(
            base_url=self.base_url,
            model=self.model,
            system=system,
            user=user,
            response_format=response_format,
            max_tokens=max(num_predict, 60),
            timeout=min(self.timeout, 20.0),
        )
        if llama_fb is not None:
            self._last_local = True  # D-075: a real local-model call (counted as a local fallback)
            return llama_fb
        return {}

    def _menu(self, context) -> list[dict]:
        from .planner import focus, refine

        canonical = context.get("canonical") or {}
        from .planner import prefer_builds

        options = _options(canonical, self.allowed)
        if self.role_handles:
            from .offices import refine_offices, retarget_create
            from .planner import home_org

            home = home_org(canonical)
            # Retarget before refine: refine drops a create whose name exists, and the engine only offers Notice.
            options = [m for m in (retarget_create(o, canonical, home) if o["action"] == "ORG_OFFICE_CREATE" else o
                                   for o in options) if m is not None]
        menu = refine(options, canonical, self.cohort_ids)
        if self.role_handles:
            menu = refine_offices(menu, canonical, home, self.role_handles, self.role_handles.get("founder"))
        if self.builds:
            menu = prefer_builds(menu, self.builds, self._built_classes())
        if self.supply and _hold_ready(canonical):
            # Hold has enough materials for a build or repair: stop gathering, spend them.
            menu = [{**o, "i": i} for i, o in enumerate(o for o in menu if o["action"] not in self.supply)]
        # D-051: SUPPLY is planner-only (need-gated, D-048); _ask hides it from the model.
        changed_subjects = _changed_published_subjects(canonical, getattr(self, "memory", None))
        menu = _one_record_per_subject(menu, self._published_subjects(), changed_subjects=changed_subjects)
        if any(o["action"] in self.verbs and o["action"] not in ("CONSTRUCT", "BUILD") for o in menu):
            # S4: role work is affordable here; the model still walked off (m04 MOVE 27/60 beside PUBLISH).
            menu = [{**o, "i": i} for i, o in enumerate(o for o in menu if o["action"] != "MOVE")]
        held_tracks = getattr(self, "held_tracks", None)
        desired_tracks = getattr(self, "focus_tracks", None) or None
        return focus(
            menu,
            self.verbs,
            getattr(self, "held_track", None),
            held_tracks=held_tracks,
            desired_tracks=desired_tracks,
        )

    def _welcome(self, canonical: dict, options: list[dict]):
        """S11: the founder greets each non-cohort Player it meets, once, naming the Compact. Planner-only."""
        from noema_client.types import ActionProposal

        from .planner import home_org

        org = home_org(canonical)
        if not org or self.memory is None:
            return None
        greeted = {t for (t,) in self.memory.db.execute("SELECT text FROM facts WHERE kind='welcomed'").fetchall()}
        for o in options:
            pid = str(o.get("target_id") or "")
            if o["action"] != "MESSAGE" or not pid or pid in greeted or pid in (self.cohort_ids or set()):
                continue
            if pid.startswith("player.reach-maint"):
                continue  # operator tier, not a recruit
            name = next((x.get("name") for x in canonical.get("organizations") or []
                         if isinstance(x, dict) and x.get("org_id") == org), None) or "the Reach Compact"
            self.memory.remember(pid, kind="welcomed", room=None, sequence=None)
            return ActionProposal(action="MESSAGE", target_id=pid, arguments={
                "recipient_id": pid,
                "text": f"Welcome to Perihelion Reach. {name} keeps the Reach standing, supplied and remembered; "
                        "ask any of us for a hand."})
        return None

    def _fuel_for_build(self, canonical: dict, options: list[dict]):
        """D-063: a treasury build costs the holder 8 energy, and an empty hold rests only to 2. Carry cargo as
        WAIT fuel (+2 each): harvest into the pack, walk to the build room, then D-062 waits and D-061 builds."""
        from noema_client.types import ActionProposal

        from .planner import route

        loc = canonical.get("location") or {}
        here = loc.get("room_id")
        built = self._built_classes()
        if self.builds and all(b in built for b in self.builds):
            # D-094: every role class is built, so no treasury build will be offered: drop the fuel run.
            self.build_room = None
            return None
        if _treasury_build_waiting(canonical, self.builds, built) or any(
                (o.get("raw") or {}).get("acting_for") and o["action"] in ("CONSTRUCT", "BUILD") for o in options):
            self.build_room = here
        goal = getattr(self, "build_room", None)
        if not goal or _vault_storage(canonical) < TREASURY_BUILD_FLOOR or self.world_map is None:
            return None
        res = canonical.get("resources") or {}
        aboard = 16 - res["storage"] if isinstance(res.get("storage"), (int, float)) else 0
        if aboard >= BUILD_FUEL_CARGO:
            if here == goal or not _can_afford_move(canonical):
                return None if here == goal else ActionProposal(action="WAIT")
            hop = self.world_map.next_hop(here, goal)
            exits = {e.get("to_room_id"): e.get("direction") for e in loc.get("exits") or [] if isinstance(e, dict)}
            return ActionProposal(action="MOVE", target_id=exits[hop]) if hop in exits else None
        pack = next((o for o in options if o["action"] == "HARVEST" and not (o.get("raw") or {}).get("acting_for")), None)
        if pack is not None:
            return _proposal(pack, self.default_args, self.memory)  # _harvest_amount sizes it (up to 8)
        if _offered_here(canonical, {"HARVEST"}):
            return ActionProposal(action="WAIT")  # D-064: harvestable here, short of energy 2: rest, don't walk off
        if not _can_afford_move(canonical):
            return None
        direction = route(canonical, self.world_map, {"HARVEST"}, explorer=False)
        return ActionProposal(action="MOVE", target_id=direction) if direction else None

    def _published_subjects(self) -> set[str]:
        if getattr(self, "memory", None) is None:
            return set()
        rows = self.memory.db.execute("SELECT text FROM facts WHERE kind='published' AND stale=0").fetchall()
        return {t for (t,) in rows}

    def _built_classes(self) -> set[str]:
        if self.memory is None:
            return set()
        rows = self.memory.db.execute("SELECT text FROM facts WHERE kind='built' AND stale=0").fetchall()
        return {t for (t,) in rows}

    def _ask(self, context, options):
        canonical = context.get("canonical") or {}
        recent = [f"{r['action']} {r.get('target') or ''}".strip() for r in self.recent[-5:]]
        # D-051: SUPPLY is planner-only (need-gated, D-048). The model spent 20/30 turns supplying blind.
        # S11: the founder's MESSAGE is planner-only too (one welcome per non-cohort Player).
        # D-059: notices are planner-only (posted when a new fact exists).
        # D-085: the model picks an index, never words, so a social option it picks always goes out textless
        # and the engine refuses it. Social verbs with text come only from the planner (notice, digest).
        hidden = set(self._hidden_verbs()) | TEXT_VERBS
        options = [{**o, "i": i} for i, o in enumerate(o for o in options if o["action"] not in hidden)]
        if not options:
            return None
        menu = [{k: o[k] for k in ("i", "action", "label")} for o in options[:24]]
        loc = canonical.get("location") or {}
        peer_ids = [str(p.get("player_id") or "") for p in canonical.get("players_here") or [] if isinstance(p, dict)]
        relations = (
            self.memory.relation_summary(peer_ids)
            if self.memory is not None and hasattr(self.memory, "relation_summary")
            else []
        )
        dt_ctx = {
            k: v
            for k, v in (
                ("scars", canonical.get("scars")),
                ("lore", canonical.get("lore_attractors")),
                ("culture", canonical.get("culture_lines")),
                ("inherited", canonical.get("inherited_lines")),
                ("rumors", canonical.get("rumor_lines")),
            )
            if v
        }
        payload = {"recent_own_actions": recent, "room": loc.get("name"), "memories": self.memories,
                   "resources": canonical.get("resources"), "options": menu}
        if relations:
            payload["peer_relations"] = relations
        if dt_ctx:
            payload["deep_time"] = dt_ctx
        user = json.dumps(payload, sort_keys=True, default=str)[:5000]
        instruction = (self.system + " Choose exactly ONE option by its index from `options`. Prefer actions unique to your role "
                       "over LOOK, INSPECT and WAIT. Use `memories` (facts you observed earlier). "
                       "Vary your actions; never pick the same option three times in a row. "
                       "Reply ONLY with JSON {\"choice\": <index>, \"why\": \"<6 words>\"}. Do not echo the input.")
        from .llm_client import build_choice_schema
        from .model_tier import tier_for

        tier = tier_for(menu)
        self._last_tier = tier
        self.stats_tier = getattr(self, "stats_tier", {})
        self.stats_tier[tier] = self.stats_tier.get(tier, 0) + 1
        if os.environ.get("NOEMA_INFERENCE_MODE", "cloud_first").strip().lower() == "local_first":
            data = self._chat(
                instruction,
                user,
                num_predict=60,
                tier=tier,
                response_format=build_choice_schema(len(menu)),
            )
        else:
            data = self._chat(instruction, user, num_predict=60, tier=tier)
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
        if not _can_afford_move(context.get("canonical") or {}):
            return ActionProposal(action="LOOK")  # a MOVE the engine will refuse is not a loop break
        exits = {e.get("to_room_id"): e.get("direction") for e in loc.get("exits") or [] if isinstance(e, dict) and e.get("direction")}
        if not exits:
            return ActionProposal(action="WAIT")
        goal = self.world_map.least_recent(sorted(r for r in exits if r)) if self.world_map is not None else None
        return ActionProposal(action="MOVE", target_id=exits.get(goal) or sorted(exits.values())[0])

    def _hidden_verbs(self) -> set[str]:
        """Planner-only verbs: neither the model nor the fallback may pick them (D-051, S11, D-059, D-067, RFC-0141 §2)."""
        verbs = getattr(self, "verbs", ())
        return (
            {"SUPPLY", "CONTRACT_POST", "SANCTION", "TRADE"}
            | ({"MESSAGE"} if "ORG_CREATE" in verbs else set())
            | ({"ORG_OFFICE_ACT"} if "MESSAGE" in verbs and "ORG_CREATE" not in verbs else set())
        )

    def _role_fallback(self, context, options):
        """Scripted choice that still honours the role: unique verbs first, then MOVE, then anything allowed."""
        tried = {(r["action"], r.get("target")) for r in self.recent[-3:]}
        hidden = self._hidden_verbs()
        options = [o for o in options if o["action"] not in hidden]
        from .planner import SHARED

        for tier in (lambda o: o["action"] not in SHARED, lambda o: o["action"] == "MOVE", lambda o: True):
            for opt in options:
                if tier(opt) and (opt["action"], opt.get("target_id")) not in tried:
                    prop = _proposal(opt, self.default_args, self.memory)
                    if prop is not None and not _needs_text(prop.action, prop.arguments):
                        return prop
        last = self.fallback.decide(context)
        act = getattr(last, "action", None)
        allowed = getattr(self, "allowed", None)
        # D-071: the generic adapter ignores the role; m05 (speaker) fell back to ORG_MEMBER_REMOVE (leave the
        # Compact) and ORG_OFFICE_VACATE (quit its Notice office). Off-role verbs become WAIT too.
        # D-085: so does a textless MESSAGE/SHOUT/BOARD, which the engine always refuses.
        if act in hidden or (allowed and act not in allowed) or _needs_text(act, getattr(last, "arguments", None)):
            # D-068: the generic adapter reads raw affordances, so it re-offered the founder's MESSAGE (183 sends).
            from noema_client.types import ActionProposal

            return ActionProposal(action="WAIT")
        return last

    def _plan(self, context, options):
        """Remember what is observed, then route if this room offers none of the role's verbs."""
        from noema_client.types import ActionProposal

        from .planner import facts_from, has_role_verb, route

        canonical = context.get("canonical") or {}
        loc = canonical.get("location") or {}
        room = loc.get("room_id")
        seq = canonical.get("sequence")
        if self.world_map is not None and room:
            res = canonical.get("resources") or {}
            if hasattr(self.world_map, "locate"):
                self.world_map.locate(canonical.get("self") or getattr(self, "self_id", None), room,
                                      res.get("energy"), res.get("storage"), seq)
            if hasattr(self.world_map, "record_work") and "ORG_CREATE" not in self.verbs:  # founder org offers are everywhere
                self.world_map.record_work(canonical.get("self") or getattr(self, "self_id", None), room,
                                           _role_work(canonical, self.verbs), seq)
            self.world_map.observe(room, loc.get("name"), seq, [e.get("to_room_id") for e in loc.get("exits") or [] if isinstance(e, dict)],
                                   [str(a.get("operation") or a.get("action") or "").upper() for a in canonical.get("affordances") or []
                                    if isinstance(a, dict) and (a.get("available") is not False or _budget_blocked(a))])
            if hasattr(self.world_map, "observe_deep_time"):
                dt_obs = self.world_map.observe_deep_time(room, canonical)
                seen = getattr(self, "deep_time_seen", None)
                if isinstance(seen, dict):
                    if dt_obs.get("scars"):
                        seen["scars"] = seen.get("scars", 0) + int(dt_obs["scars"])
                    if dt_obs.get("lore"):
                        seen["lore"] = seen.get("lore", 0) + int(dt_obs["lore"])
                    if dt_obs.get("culture"):
                        seen["culture"] = seen.get("culture", 0) + int(dt_obs["culture"])
                    if canonical.get("inherited_lines"):
                        seen["inherited"] = seen.get("inherited", 0) + len(canonical.get("inherited_lines") or [])
            if hasattr(self.world_map, "observe_market_and_equipment"):
                self.world_map.observe_market_and_equipment(
                    room,
                    canonical.get("self") or getattr(self, "self_id", None),
                    canonical,
                )
            if hasattr(self.world_map, "observe_shared_work"):
                self.world_map.observe_shared_work(
                    room,
                    canonical.get("self") or getattr(self, "self_id", None),
                    canonical,
                )
        if self.memory is not None:
            facts = facts_from(canonical)
            for kind, text in facts:
                self.memory.remember(text, kind=kind, room=room, sequence=seq)
            self.memory.mark_stale(kind="offer", room=room, keep={t for k, t in facts if k == "offer"})
            self._record_social_evidence(canonical, seq)
            for ent in loc.get("entities") or canonical.get("entities") or []:
                cls = isinstance(ent, dict) and ent.get("entity_type") == "INFRASTRUCTURE" and (
                    ent.get("infra_type") or str(ent.get("label") or "").replace("-", "_"))
                if cls and not ent.get("in_progress"):
                    self.memory.remember(str(cls), kind="built", room=room, sequence=seq)
            self.memories = self.memory.recall(" ".join([str(loc.get("name") or "")] + sorted(self.verbs)))
            self.stats_mem += len(self.memories)
        from .playbooks import PlaybookContext, run_role_playbook

        role_name = str(getattr(getattr(self, "health", None), "role", "") or "").rsplit("-", 1)[-1]
        knobs_now = getattr(self, "policy_knobs", None) or {}
        traits_now = getattr(self, "persona_traits", None) or {}
        mgr = getattr(self, "agenda_manager", None)
        if mgr is not None and seq is not None and mgr.needs_refresh(sum(self.stats.values()), int(seq)):
            mgr.refresh(
                role=role_name,
                canonical=canonical,
                world_map=self.world_map,
                traits=traits_now,
                current_seq=int(seq),
                turn_count=sum(self.stats.values()),
                me=getattr(self, "self_id", None),
            )
        ctx = PlaybookContext(
            adapter=self,
            canonical=canonical,
            options=options,
            role_name=role_name,
            room_id=room,
            seq=seq,
            knobs=knobs_now,
            traits=traits_now,
        )
        res = run_role_playbook(ctx)
        self.last_playbook_state = res.state if res is not None else None
        return res.proposal if res is not None else None

    def _record_social_evidence(self, canonical: dict, seq) -> None:
        """Record observed co-located peer / rumor evidence into memory.db relations table."""
        if self.memory is None or not hasattr(self.memory, "note_player"):
            return
        cons = str(canonical.get("last_consequence") or "")
        low = cons.lower()
        for peer in canonical.get("players_here") or []:
            if not isinstance(peer, dict):
                continue
            pid = str(peer.get("player_id") or "")
            handle = str(peer.get("handle") or "")
            if not pid or not handle or handle.lower() not in low:
                continue
            if any(w in low for w in ("supplied", "repaired", "corroborated", "agreed", "welcomed", "shared", "vested")):
                self.memory.note_player(pid, cons[:180], sign=1, sequence=seq)
            elif any(w in low for w in ("refused", "contested", "broken", "denied", "disrupted")):
                self.memory.note_player(pid, cons[:180], sign=-1, sequence=seq)
        for line in canonical.get("rumor_lines") or []:
            txt = str(line or "")
            if txt.startswith("You heard a report from "):
                who = txt.removeprefix("You heard a report from ").rstrip(".")
                if who and who != "an unknown source":
                    self.memory.note_player(who, txt[:180], sign=1, sequence=seq)

    def decide(self, context):
        from .nvtx_trace import nvtx_range
        from .planner import has_role_verb

        self.self_id = (context.get("canonical") or {}).get("self") or getattr(self, "self_id", None)
        if self.on_turn is not None:
            self.cohort_ids = self.on_turn(self.self_id)
        options = self._menu(context)
        source = "model"
        try:
            with nvtx_range("playbook_plan"):
                proposal = self._plan(context, options)
        except Exception as exc:  # memory must never stall a turn
            print(json.dumps({"memory_error": type(exc).__name__}), flush=True)
            proposal = None
        if proposal is not None:
            source = "planner"
            self.stats["planner"] += 1
        elif not has_role_verb(options, self.verbs | set(self.supply or ())):
            # D-042: nothing in role on offer; the model can only pick LOOK/WAIT/MOVE/INSPECT. Script it.
            # D-044: walk toward the role's goal room first (the dwell gate made idle WAITs loop in place);
            # WAIT only when there is no route or the move is unaffordable.
            from noema_client.types import ActionProposal

            from .planner import route

            canonical = context.get("canonical") or {}
            goal = self.supply if (self.supply and _hold_empty(canonical)) else self.verbs
            direction = None
            stay = set(goal) - STAY_EXEMPT
            if _offered_here(canonical, stay, done=self._published_subjects()):
                # S4: the role verb is here, only unaffordable now (filtered from options). WAIT refuels in place;
                # m03 walked away from relay-quarter REPAIR at energy 3 every time it arrived.
                pass
            elif (self.world_map is not None and "ORG_CREATE" not in self.verbs
                    and _can_afford_move(canonical) and (not self.allowed or "MOVE" in self.allowed)
                    and _energy_after_move_ok(canonical, self.explorer)):
                # The founder (ORG_CREATE) stays put: its raw org offers are everywhere and get filtered.
                direction = route(
                    canonical,
                    self.world_map,
                    _route_verbs(set(goal)),
                    explorer=self.explorer,
                    me=getattr(self, "self_id", None),
                    current_seq=canonical.get("sequence"),
                )
            proposal = ActionProposal(action="MOVE", target_id=direction) if direction else ActionProposal(action="WAIT")
            source = "idle_skip"
            self.stats["idle_skip"] = self.stats.get("idle_skip", 0) + 1
        else:
            try:
                proposal = self._ask(context, options)
            except Exception:
                proposal = None
        if source in ("planner", "idle_skip"):
            pass
        elif proposal is not None:
            self.stats["model"] += 1
        else:
            source = "fallback"
            self.stats["fallback"] += 1
            proposal = self._role_fallback(context, options)
        key = (getattr(proposal, "action", None), getattr(proposal, "target_id", None))
        if key[0] == "ORG_OFFICE_CREATE" and not _create_allowed(context.get("canonical") or {}, proposal):
            # D-066: hard gate. m01 created 30 Notice offices: each create named an office that already existed.
            from noema_client.types import ActionProposal

            source, proposal = "guard", ActionProposal(action="WAIT")
            key = ("WAIT", None)
        refuel_wait = (source == "planner" and key[0] == "WAIT"
                       and _wait_refuels((context.get("canonical") or {}).get("resources") or {}))
        if (len(self.recent) >= 2 and not refuel_wait
                and all((r["action"], r.get("target")) == key for r in self.recent[-2:])):
            from noema_client.types import ActionProposal

            source = "loop_break"
            self.stats["loop_break"] += 1
            if _depleted(context.get("canonical") or {}):
                proposal = ActionProposal(action="WAIT")
            else:
                proposal = self._loop_break_move(context) if key[0] != "MOVE" else ActionProposal(action="LOOK")
        prop_args = getattr(proposal, "arguments", None) or {}
        rec_entry = {
            "action": getattr(proposal, "action", None),
            "target": getattr(proposal, "target_id", None),
        }
        if prop_args.get("phase"):
            rec_entry["phase"] = str(prop_args["phase"])
        self.recent = (self.recent + [rec_entry])[-40:]
        track = (getattr(proposal, "arguments", None) or {}).get("track")
        subject = (getattr(proposal, "arguments", None) or {}).get("subject_ref")
        if (str(getattr(proposal, "action", "") or "").upper() == "RECONSTRUCT_PUBLISH" and subject
                and self.memory is not None):
            # S12: one public record per subject; also snapshot its observed state fingerprint (T6/#160).
            self.memory.remember(str(subject), kind="published", room=None, sequence=None)
            fp = _subject_state_fingerprint(context.get("canonical") or {}, str(subject))
            if fp:
                self.memory.remember(fp, kind="subject_state", room=None, sequence=(context.get("canonical") or {}).get("sequence"))
        if (str(getattr(proposal, "action", "") or "").upper() == "RECONSTRUCT_SUPERSEDE" and subject
                and self.memory is not None):
            self.memory.remember("revised:" + str(subject), kind="published", room=None, sequence=None)
            fp = _subject_state_fingerprint(context.get("canonical") or {}, str(subject))
            if fp:
                self.memory.remember(fp, kind="subject_state", room=None, sequence=(context.get("canonical") or {}).get("sequence"))
        if str(getattr(proposal, "action", "") or "").upper() == "AGREEMENT_FORM" and self.memory is not None:
            args = getattr(proposal, "arguments", None) or {}
            party = args.get("player_id") or getattr(proposal, "target_id", None)
            if party:
                self.memory.remember(f"agreement:{party}", kind="published", room=None, sequence=None)
        if str(getattr(proposal, "action", "") or "").upper() in ("FOCUS", "COMMIT.FOCUS") and track:
            t_norm = str(track).strip().lower()
            held = list(getattr(self, "held_tracks", None) or [])
            if t_norm in held:
                held.remove(t_norm)
            held.append(t_norm)
            self.held_tracks = held[-2:]
            self.held_track = self.held_tracks[-1]  # D-049 + RFC-0144 §1 dual-track cap
        if str(getattr(proposal, "action", "") or "").upper() in ("MESSAGE", "SHOUT", "BOARD"):
            self._last_social_turn = sum(self.stats.values())
        canonical = (context.get("canonical") or {})
        act_upper = str(getattr(proposal, "action", "") or "").upper()
        tgt_id = getattr(proposal, "target_id", None)
        if (
            self.world_map is not None
            and hasattr(self.world_map, "claim_target")
            and act_upper in ("REPAIR", "RESTORE", "REMEDIATE", "CONTRACT_FULFILL", "INVESTIGATE")
            and tgt_id
            and self.self_id
        ):
            self.world_map.claim_target(str(tgt_id), str(self.self_id), act_upper, int(canonical.get("sequence") or 0))
        if getattr(self, "agenda_manager", None) is not None:
            self.agenda_manager.mark_progress(
                canonical=canonical,
                action=act_upper,
                target_id=str(tgt_id) if tgt_id else None,
                current_seq=int(canonical.get("sequence") or 0),
            )
        cyc = canonical.get("cycle")
        if isinstance(cyc, int) and cyc > 0:
            self.last_cycle = cyc
        self.health.record_turn(
            verb=str(getattr(proposal, "action", "") or ""),
            used_workers_ai=bool(getattr(self, "_last_remote", False)),
            used_planner=source in ("planner", "idle_skip", "guard"),
            used_local=bool(getattr(self, "_last_local", False)),
            used_local_s1=bool(getattr(self, "_last_local_s1", False)),
            source_sequence=int(canonical.get("sequence") or 0),
        )
        self._last_remote = False
        self._last_local = False
        self._last_local_s1 = False
        budgets_snap = {k: v for k, v in (canonical.get("resources") or {}).items()
                        if k in ("energy", "attention", "compute", "storage", "influence")}
        if hasattr(self, "turn_log"):
            from .shop_planner import count_unequipped_broken_tools

            self.turn_log.append({
                "seq": canonical.get("sequence"),
                "room": (canonical.get("location") or {}).get("room_id"),
                "action": getattr(proposal, "action", None),
                "target": getattr(proposal, "target_id", None),
                "source": source,
                "budgets": budgets_snap,
                "unequipped_broken_tools": count_unequipped_broken_tools(canonical),
                "consequence": canonical.get("last_consequence"),
            })
        shadow = self._shadow_consequence(canonical, proposal)
        turn_line = {"turn": sum(self.stats.values()), "source": source,
                          "action": getattr(proposal, "action", None),
                          "target": getattr(proposal, "target_id", None),
                          "args_keys": sorted((getattr(proposal, "arguments", None) or {}).keys()),
                          "memories_used": len(self.memories),
                          "budgets": budgets_snap,
                          "tier": getattr(self, "_last_tier", None) if source == "model" else None,
                          "room": (canonical.get("location") or {}).get("room_id"),
                          "offered_supply": sorted({o["action"] for o in options} & set(self.supply or ())),
                          "blocked": sorted({str(a.get("action") or "").upper() + ":" + str(a.get("reason") or "")[:40]
                                              for a in canonical.get("affordances") or []
                                              if isinstance(a, dict) and a.get("available") is False
                                              and str(a.get("action") or "").upper() in (self.verbs | set(self.supply or ()))})[:4],
                          "offered_role": sorted({o["action"] for o in options} & self.verbs)}
        if source == "planner" and self.last_playbook_state:
            turn_line["step"] = self.last_playbook_state  # D-092: which playbook rule chose a planner turn
        if shadow is not None:
            turn_line["consequence"] = shadow  # C3 (#198): INFERRED estimate for the chosen action; telemetry only
        print(json.dumps(turn_line), flush=True)
        self._last_tier = None
        batch_cap = int((getattr(self, "policy_knobs", None) or {}).get("harvest_batch_target", HARVEST_MAX))
        if not hasattr(self, "_vault_seen"):
            self._vault_seen = {}
        _remember_vaults(self._vault_seen, canonical)
        proposal = _harvest_amount(proposal, canonical, max_batch=batch_cap, known_vaults=self._vault_seen)
        transition_log = getattr(self, "transition_log", None)
        if transition_log is not None:
            # D-078: opt-in, Controller-local. Logs the proposal as returned; must never stall a turn.
            try:
                transition_log.append(canonical=canonical, proposal=proposal, source=source)
            except Exception as exc:
                print(json.dumps({"transition_log_error": type(exc).__name__}), flush=True)
        return proposal


def _create_allowed(canonical: dict, proposal) -> bool:
    """Only create an office the catalog lacks, by name, in the home org. Anything else is a duplicate."""
    from .offices import _home, missing
    from .planner import home_org

    home = home_org(canonical)
    args = getattr(proposal, "arguments", None) or {}
    name = args.get("display_name") or args.get("name")
    if not home or args.get("org_id") not in (None, home):
        return False
    offices = _home(canonical, home).get("offices")
    if not offices:
        return False  # observation without the home org's offices: everything would look missing
    existing = {str(o.get("display_name")) for o in offices if isinstance(o, dict)}
    return bool(name) and name not in existing and name in {n for n, _p in missing(canonical, home)}


def _subject_state_fingerprint(canonical: dict, subject_ref: str) -> str | None:
    """Compute a coarse observed state fingerprint for a subject so m04 supersedes only on real state deltas (T6/#160)."""
    loc = canonical.get("location") or {}
    ents = [e for e in (loc.get("entities") or canonical.get("entities") or []) if isinstance(e, dict)]
    ent = next((e for e in ents if str(e.get("entity_id") or "") == subject_ref), None)
    if ent is None and str(loc.get("room_id") or "") != subject_ref:
        return None
    cond_raw = ent.get("condition") if ent is not None else None
    cond_bucket = (int(cond_raw) // 20) * 20 if isinstance(cond_raw, (int, float)) else -1
    scar_count = len([s for s in (canonical.get("scars") or []) if isinstance(s, dict) and s.get("scar_id")])
    contest_count = len([c for c in (canonical.get("contests") or []) if isinstance(c, dict) and c.get("status") == "OPEN"])
    return f"{subject_ref}|cond={cond_bucket}|scars={scar_count}|contests={contest_count}"


def _changed_published_subjects(canonical: dict, memory) -> set[str]:
    """Return subject_refs whose live observed fingerprint differs from their latest stored subject_state (T6/#160)."""
    if memory is None:
        return set()
    rows = memory.db.execute(
        "SELECT text FROM facts WHERE kind='subject_state' AND stale=0 ORDER BY coalesce(source_sequence, 0) ASC, id ASC"
    ).fetchall()
    latest: dict[str, str] = {}
    for (txt,) in rows:
        if "|" in str(txt or ""):
            subj = str(txt).split("|", 1)[0]
            latest[subj] = str(txt)
    changed: set[str] = set()
    for subj, recorded in latest.items():
        live = _subject_state_fingerprint(canonical, subj)
        if live is not None and live != recorded:
            changed.add(subj)
    return changed


def _one_record_per_subject(
    menu: list[dict],
    published: set[str],
    *,
    changed_subjects: set[str] | frozenset[str] = frozenset(),
) -> list[dict]:
    """S12 + D-070 + T6/#160: one PUBLISH per subject; permit SUPERSEDE once per subject OR on observed state delta."""
    seen, kept = set(published), []
    for o in menu:
        raw = o.get("raw") or {}
        subject = raw.get("subject_ref")
        if o["action"] == "RECONSTRUCT_PUBLISH" and subject:
            if subject in seen:
                continue
            seen.add(subject)
        elif o["action"] == "RECONSTRUCT" and subject and subject in published:
            continue
        elif o["action"] == "RECONSTRUCT_SUPERSEDE" and subject:
            # D-070 + T6/#160: suppress unchanged revisions, but re-allow when subject state fingerprint changed.
            key = "revised:" + str(subject)
            if key in seen and subject not in changed_subjects:
                continue
            seen.add(key)
        elif o["action"] == "AGREEMENT_FORM":
            # D-072: m01 tried 46 agreements in 200 turns (25 at Cantor), mostly NOT_COLOCATED. One offer per party.
            party = raw.get("player_id") or o.get("target_id")
            key = f"agreement:{party}"
            if key in seen:
                continue
            seen.add(key)
        kept.append(o)
    return kept if len(kept) == len(menu) else [{**o, "i": i} for i, o in enumerate(kept)]


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
            if budget == "energy" and not _wait_refuels(res):
                continue  # D-033: WAIT at energy 1+ with an empty hold restores nothing
            need = (aff.get("requires") or {}).get(budget)
            have = res.get(budget)
            if isinstance(need, (int, float)) and isinstance(have, (int, float)) and have < need and budget in reason:
                return True
    return False


HARVEST_MAX = 8  # D-032: leaves hold room; cargo MOVE costs +1 regardless of amount
SPEND_READY = 5  # D-050: cargo MOVE 2 + REPAIR 3 (engine COSTS)
# D-052: CONSTRUCT is offered in every room, so routing on it walks to whichever room was seen last.
UBIQUITOUS = frozenset({"CONSTRUCT", "BUILD"})
# D-069: FOCUS is offered in every room; holding it already, m06 WAITed in place 257/385 turns at energy 80.
STAY_EXEMPT = frozenset({"FOCUS", "COMMIT.FOCUS"})
# D-085: the engine refuses these without text, and an affordance never carries any (`message tester "hello"`
# maps to {kind: social}). Only a planner step that wrote grounded text may send one.
TEXT_VERBS = frozenset({"MESSAGE", "SHOUT", "BOARD"})


def _needs_text(action, arguments) -> bool:
    """True when `action` is a social verb and `arguments` carry no text to say (D-085)."""
    if str(action or "").upper() not in TEXT_VERBS:
        return False
    return not str((arguments or {}).get("text") or "").strip()


def _route_verbs(verbs) -> set[str]:
    """Route on the verbs that pick out a room; keep CONSTRUCT only when nothing else is left."""
    v = set(verbs)
    return (v - UBIQUITOUS) or v
SUPPLY_AMOUNT = 3  # D-047: under the engine cap of 5; spreads the vault across peers
LOW_ENERGY = 3  # D-048: a cohort peer at or below this recorded energy with an empty hold gets cargo (WAIT fuel)
LOW_CARGO = 6  # D-048: custodian with fewer than this aboard (16 - free) gets cargo


def _can_supply(opt: dict, canonical: dict) -> tuple[bool, int]:
    """T3/#157: verify SUPPLY colocation, active OPERATE_RESOURCE_ACCOUNT office, and live vault storage."""
    raw = opt.get("raw") or {}
    pid = str(opt.get("target_id") or raw.get("player_id") or "")
    if not pid:
        return False, 0
    if "players_here" in canonical:
        here_ids = {str(p.get("player_id") or "") for p in canonical.get("players_here") or [] if isinstance(p, dict)}
        if pid not in here_ids:
            return False, 0
    orgs = [o for o in (canonical.get("organizations") or []) if isinstance(o, dict)]
    vault = _vault_storage(canonical) if orgs else SUPPLY_AMOUNT
    if orgs and vault < 1:
        return False, 0
    me = str(canonical.get("self") or "")
    me_handle = me.replace("player.", "", 1)
    if orgs and me:
        all_offices = [
            off
            for o in orgs
            for off in (o.get("offices") or [])
            if isinstance(off, dict)
        ]
        if all_offices:
            holds_res = any(
                str(off.get("authority_profile") or off.get("profile") or "") == "OPERATE_RESOURCE_ACCOUNT"
                and str(off.get("status") or "OCCUPIED") == "OCCUPIED"
                and (str(off.get("holder_id") or "") == me or str(off.get("holder_handle") or "") == me_handle)
                for off in all_offices
            )
            if not holds_res:
                return False, 0
    return True, max(1, min(SUPPLY_AMOUNT, int(vault)))


def _needs_supply(opt: dict, custodian: str | None, world_map, cohort_ids) -> bool:
    """D-048: supply only on recorded need. Positions are each agent's own observation (shared map.db).

    The treasury fills with cargo only (treasury harvest), so cargo is the service. The custodian spends it on
    REPAIR/RESTORE. Any low-energy cohort peer with an empty hold gets it too, because WAIT burns 1 cargo for
    +2 energy (RFC-0119): a peer stuck at energy 0-1 with nothing aboard has no other way back.
    """
    raw = opt.get("raw") or {}
    if raw.get("resource") != "storage":
        return False
    pid = str(opt.get("target_id") or raw.get("player_id") or "")
    pos = world_map.position(pid) if world_map is not None and hasattr(world_map, "position") else None
    free = pos[2] if pos and isinstance(pos[2], (int, float)) else None
    aboard = None if free is None else 16 - free
    if custodian and pid.replace("player.", "", 1) == custodian:
        blocked = hasattr(world_map, "work_for") and bool(world_map.work_for(pid, need="materials"))
        return aboard is None or aboard < LOW_CARGO or blocked  # S8: its own work is waiting on materials
    if cohort_ids and pid not in cohort_ids:
        return False
    energy = pos[1] if pos and isinstance(pos[1], (int, float)) else None
    return energy is not None and energy <= LOW_ENERGY and aboard == 0
TREASURY_CAP = 64  # engine TREASURY_STORAGE_CAP (RFC-0133)
TREASURY_BUILD_FLOOR = 12  # D-061: build cost (5-6) + two SUPPLYs (3 each) stay in the vault
BUILD_FUEL_CARGO = 4  # D-063: 4 cargo x WAIT +2 = 8 energy, a generator's holder share


def _treasury_build_waiting(canonical: dict, builds, built=()) -> bool:
    """A treasury build of a role class is offered here and blocked only on the holder's own resources.
    D-094: a class already built is not waited for; `prefer_builds` drops its CONSTRUCT from the menu."""
    want = {b for b in builds if b not in set(built)}
    return any(isinstance(a, dict) and a.get("acting_for") and str(a.get("operation") or "").upper() == "CONSTRUCT"
               and a.get("available") is False and str(a.get("class") or "") in want
               and "treasury" not in str(a.get("reason") or "").lower()
               for a in canonical.get("affordances") or [])


def _vault_storage(canonical: dict) -> int:
    return int(max([(o.get("treasury") or {}).get("storage") or 0 for o in canonical.get("organizations") or []
                    if isinstance(o, dict)] or [0]))


def _toward_needy_custodian(canonical: dict, custodian: str | None, world_map) -> str | None:
    """S7: exit toward the custodian when it is short of cargo (D-048 LOW_CARGO) and the vault can cover a supply."""
    if not custodian or world_map is None or not hasattr(world_map, "position"):
        return None
    vault = max([(o.get("treasury") or {}).get("storage") or 0 for o in canonical.get("organizations") or []
                 if isinstance(o, dict)] or [0])
    if vault < SUPPLY_AMOUNT:
        return None
    pos = world_map.position(f"player.{custodian}")
    blocked = hasattr(world_map, "work_for") and bool(world_map.work_for(f"player.{custodian}", need="materials"))
    if not pos or not isinstance(pos[2], (int, float)) or (16 - pos[2] >= LOW_CARGO and not blocked):
        return None
    loc = canonical.get("location") or {}
    here = loc.get("room_id")
    if not here or pos[0] == here:
        return None
    hop = world_map.next_hop(here, pos[0])
    exits = {e.get("to_room_id"): e.get("direction") for e in loc.get("exits") or [] if isinstance(e, dict)}
    return exits.get(hop) if hop else None


def _vault_harvest_amount(opt: dict, canonical: dict) -> int:
    """Treasury harvest skips the pack, so only node stock and the vault cap bound it."""
    target = opt.get("target_id")
    loc = canonical.get("location") or {}
    stock = next((e.get("stock_amount") for e in (loc.get("entities") or canonical.get("entities") or [])
                  if isinstance(e, dict) and e.get("entity_id") == target), 1)
    org = (opt.get("raw") or {}).get("acting_for")
    vault = next(((o.get("treasury") or {}).get("storage") or 0 for o in canonical.get("organizations") or []
                  if isinstance(o, dict) and o.get("org_id") == org), 0)
    return max(1, int(min(HARVEST_MAX, stock if isinstance(stock, (int, float)) else 1, TREASURY_CAP - vault)))


def _remember_vaults(seen: dict, canonical: dict) -> None:
    """D-091: keep the last treasury storage seen per org; a stripped observation never erases it."""
    for o in canonical.get("organizations") or []:
        if isinstance(o, dict) and o.get("org_id") and isinstance(o.get("treasury"), dict):
            storage = o["treasury"].get("storage")
            if isinstance(storage, (int, float)):
                seen[o["org_id"]] = storage


def _harvest_amount(proposal, canonical: dict, *, max_batch: int = HARVEST_MAX, known_vaults: dict | None = None):
    """HARVEST costs 2 energy flat and WAIT burns 1 cargo for +2 energy, so amount 1 only breaks even.

    Take up to max_batch, bounded by free storage and the node's visible stock.
    D-091: a treasury harvest (`acting_for`) goes to the org vault, not the pack, so the vault headroom bounds
    it, from this observation or else the last level seen. With neither, the planner's amount stands.
    """
    if proposal is None or str(getattr(proposal, "action", "")).upper() != "HARVEST":
        return proposal
    org = (proposal.arguments or {}).get("acting_for")
    if org:
        vault = next(((o.get("treasury") or {}).get("storage") for o in canonical.get("organizations") or []
                      if isinstance(o, dict) and o.get("org_id") == org and isinstance(o.get("treasury"), dict)), None)
        if not isinstance(vault, (int, float)):
            vault = (known_vaults or {}).get(org)
        if isinstance(vault, (int, float)):
            asked = int((proposal.arguments or {}).get("amount") or 1)
            proposal.arguments = {**(proposal.arguments or {}),
                                  "amount": max(1, min(asked, int(TREASURY_CAP - vault)))}
        return proposal
    free = (canonical.get("resources") or {}).get("storage")
    if not isinstance(free, (int, float)) or free < 2:
        return proposal
    target = getattr(proposal, "target_id", None) or (proposal.arguments or {}).get("entity_id")
    loc = canonical.get("location") or {}
    stock = next((e.get("stock_amount") for e in (loc.get("entities") or canonical.get("entities") or [])
                  if isinstance(e, dict) and e.get("entity_id") == target), None)
    if not isinstance(stock, (int, float)):
        return proposal
    amount = int(min(max(1, max_batch), free, stock))
    if amount > 1:
        proposal.arguments = {**(proposal.arguments or {}), "amount": amount}
    return proposal


ATTENTION_VERBS = frozenset({"RECONSTRUCT", "RECONSTRUCT_PUBLISH", "RECONSTRUCT_SUPERSEDE", "ATTEST"})  # engine: attention 2


def _energy_after_move_ok(canonical: dict, explorer: bool) -> bool:
    """S3/S6: walk only when arriving leaves energy for something. Explorers need 2 (arrive at 1, can LOOK and
    still WAIT-rest); m06 spent 38/60 turns at energy <= 1 bouncing MOVE/WAIT. Others keep D-034 (spend the 1)."""
    energy = (canonical.get("resources") or {}).get("energy")
    if not explorer or not isinstance(energy, (int, float)):
        return True
    return energy >= 2


def _role_work(canonical: dict, verbs) -> list[tuple[str, str, str]]:
    """S8/S10: (operation, target, need) for role verbs advertised here, except CONSTRUCT/BUILD (everywhere) and
    depleted nodes. need '' = affordable now."""
    out = []
    for a in canonical.get("affordances") or []:
        if not isinstance(a, dict):
            continue
        op = str(a.get("operation") or a.get("action") or "").upper()
        if op not in verbs or op in ("CONSTRUCT", "BUILD") or not (a.get("available") is not False or _budget_blocked(a)):
            continue
        reason = str(a.get("reason") or "").lower()
        need = ("" if a.get("available") is not False else "materials" if "material" in reason
                else "energy" if "energy" in reason else "attention" if "attention" in reason else "other")
        out.append((op, str(a.get("target_id") or ""), need))
    return out


def _budget_blocked(aff: dict) -> bool:
    """S4: offered but unaffordable for a budget or cargo reason, so the room still has the work.
    "Not enough stock" means the node is depleted: the work is gone."""
    return "stock" not in str(aff.get("reason") or "").lower()


def _depleted(canonical: dict) -> bool:
    """Energy 0: only WAIT recovers it (engine applyLockoutRest, any hold since #910)."""
    energy = (canonical.get("resources") or {}).get("energy")
    return isinstance(energy, (int, float)) and energy <= 0


def _offered_here(canonical: dict, verbs: set[str], done: set[str] | frozenset = frozenset()) -> bool:
    """D-035: the room advertises a role verb even if unaffordable now; stay and rest rather than walk off.
    S4: a depleted node ("Not enough stock") does not count; WAIT cannot fix it.
    D-073: neither does a record of an already-published subject (m04 WAITed 181/600 beside 125 such offers)."""
    return any(isinstance(a, dict) and str(a.get("operation") or a.get("action") or "").upper() in verbs
               and (a.get("available") is not False or _budget_blocked(a))
               and not (str(a.get("action") or "").startswith("RECONSTRUCT") and a.get("subject_ref") in done)
               for a in canonical.get("affordances") or [])


def _wait_refuels(res: dict) -> bool:
    """Engine: WAIT gives energy at energy < 2 with an empty hold (RFC-0117 amendment 1, Noema#926), at energy 0
    with a full hold (lockout rest), or with cargo aboard (RFC-0119 cargo fuel)."""
    energy, storage = res.get("energy"), res.get("storage")
    if not isinstance(energy, (int, float)) or not isinstance(storage, (int, float)):
        return True
    return energy <= 0 or storage < 16 or energy < 2


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


def _requires_met(aff: dict, resources: dict) -> bool:
    """T3/#157: drop affordances whose explicit budget `requires` exceed current canonical resources."""
    req = aff.get("requires")
    if not isinstance(req, dict) or not isinstance(resources, dict) or not resources:
        return True
    for budget in ("energy", "attention", "compute", "storage"):
        need = req.get(budget)
        have = resources.get(budget)
        if isinstance(need, (int, float)) and isinstance(have, (int, float)) and have < need:
            return False
    return True


def _options(canonical: dict, allowed: frozenset) -> list[dict]:
    """Available advertised affordances this role may use, as a short indexed menu.

    `action` is the operation the server executes (ORG_INVITE -> ORG_MEMBER_ADD) and
    `raw` is kept so the proposal is built by the client's own affordance mapper.
    """
    resources = canonical.get("resources") if isinstance(canonical.get("resources"), dict) else {}
    out = []
    for aff in canonical.get("affordances") or []:
        if not isinstance(aff, dict) or aff.get("available") is False:
            continue
        if not _requires_met(aff, resources):
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


def _proposal(opt: dict, default_args: dict, memory=None, *, world_map=None, canonical: dict | None = None):
    from noema_client.affordances import proposal_from_affordance
    from noema_client.types import ActionProposal

    base = proposal_from_affordance(opt["raw"]) if opt.get("raw") else None
    if base is None:
        return ActionProposal(action=opt["action"], target_id=opt.get("target_id"), arguments=dict(default_args.get(opt["action"], {})))
    args = {**default_args.get(base.action, {}), **_cmd_args(opt["raw"]), **dict(base.arguments or {})}
    if base.action == "CONVERT" and not args.get("convert_mode"):
        # D-097: noema-client 0.2.0 drops `convert_mode` (not in ARGUMENT_KEYS); the engine refuses CONVERT without it.
        raw = opt["raw"]
        mode = raw.get("convert_mode") or next(
            (w for w in str(raw.get("cmd") or "").split() if w in ("power", "compute")), None)
        if mode:
            args["convert_mode"] = mode
    if base.action == "SUPPLY":
        args.setdefault("amount", SUPPLY_AMOUNT)  # engine requires 1..5; model-picked SUPPLY carried none
    if base.action == "ORG_OFFICE_ACT":
        if not args.get("org_id"):
            return None  # T3/#157: ORG_OFFICE_ACT without org_id fails INVALID_REQUEST
        if not args.get("notice") and not args.get("governance_rule"):
            notice = grounded_notice(memory, world_map=world_map, canonical=canonical)
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


def grounded_market_and_contract_digest(
    memory,
    world_map,
    canonical: dict | None = None,
    org_name: str = "Reach Compact",
) -> str | None:
    """Grounded TRADE_NOTICE / BOARD digest of active barter_stall stock and open WS06 contracts (RFC-0141 §2.2, T6/#160)."""
    if memory is None or world_map is None or not hasattr(world_map, "observed_listings"):
        return None
    listings = [l for l in world_map.observed_listings() if int(l.get("fills_remaining") or 0) > 0]
    contracts = [c for c in ((canonical or {}).get("open_contracts") or []) if isinstance(c, dict)]
    if not listings and not contracts:
        return None
    seq_candidates = [int(l.get("seen_seq") or 0) for l in listings]
    if canonical and isinstance(canonical.get("sequence"), int) and not seq_candidates:
        seq_candidates.append(int(canonical["sequence"]))
    obs_seq = max(seq_candidates) if seq_candidates else 0
    parts: list[str] = []
    if listings:
        summaries = []
        for l in listings[:3]:
            kind = str(l.get("listing_kind") or "OFFER")
            offer_s = str(l.get("offer_json") or "")
            ask_s = str(l.get("ask_json") or "")
            item_tag = ""
            for token in ("power_cell", "chrono_lens", "arc_welder", "plasma_cutter", "signal_transceiver", "FERROUS_ORE", "SALVAGE_COMPOSITE", "SILICA_CELL"):
                if token in offer_s or token in ask_s:
                    item_tag = f"({token})"
                    break
            summaries.append(f"{kind}{item_tag}")
        # D-096: name the room the stall stands in (the Compact's is in the Archive, D-092); "Exchange stall" sent
        # readers to Civic Exchange, where none stands. Group by room; fall back to the room id when no name is known.
        rooms: list[str] = []
        for l in listings[:3]:
            rid = str(l.get("room_id") or "")
            if rid and rid not in rooms:
                rooms.append(rid)
        names = []
        for rid in rooms:
            row = world_map.db.execute("SELECT name FROM rooms WHERE room_id=?", (rid,)).fetchone() if hasattr(world_map, "db") else None
            names.append((row[0] if row and row[0] else rid))
        where = " / ".join(names) if names else "Market"
        parts.append(f"{where} stall: " + ", ".join(summaries))
    if contracts:
        c_summaries = []
        for c in contracts[:2]:
            ck = str(c.get("kind") or "CONTRACT")
            detail = c.get("target_item_archetype") or c.get("target_material") or ""
            c_summaries.append(f"{ck}({detail})" if detail else ck)
        parts.append("Open contracts: " + ", ".join(c_summaries))
    core = "; ".join(parts)
    dedup_key = f"trade_digest:{core}|seq={obs_seq}"
    posted = {t for (t,) in memory.db.execute("SELECT text FROM facts WHERE kind='noticed'").fetchall()}
    if dedup_key in posted:
        return None
    memory.remember(dedup_key, kind="noticed", room=None, sequence=obs_seq)
    return f"{org_name} TRADE_NOTICE: {core} (observed at seq {obs_seq})"[:280]


def grounded_notice(
    memory,
    org_name: str = "the Compact",
    *,
    world_map=None,
    canonical: dict | None = None,
) -> str | None:
    """A public notice built only from observed, non-stale facts, citing the source sequence (S13, T6/#160).

    D-059: skip the speaker's own echoes ("Notice posted", "You wait", "You arrive"): m05 was publishing its last
    consequence, which was usually its previous notice. One notice per fact (kind `noticed`)."""
    if memory is None:
        return None
    if world_map is not None:
        digest_notice = grounded_market_and_contract_digest(memory, world_map, canonical, org_name=org_name)
        if digest_notice:
            return digest_notice
    posted = {t for (t,) in memory.db.execute("SELECT text FROM facts WHERE kind='noticed'").fetchall()}
    rows = memory.db.execute(
        "SELECT text, source_sequence FROM facts WHERE stale=0 AND kind IN ('consequence','room') "
        "AND text NOT LIKE 'You %' AND text NOT LIKE 'Enter the world%' AND text NOT LIKE 'Notice posted%' "
        "AND text NOT LIKE 'Reconstruction published%' AND text NOT LIKE 'Welcome to%' "
        "AND text NOT LIKE '%Open ground%' "
        "ORDER BY sequence DESC LIMIT 12").fetchall()
    row = next((r for r in rows if r[0] not in posted), None)
    if not row:
        return None
    text, seq = row
    memory.remember(text, kind="noticed", room=None, sequence=seq)
    return f"{org_name} notice: {text} (observed at seq {seq})"[:280]


AGENT_OPS = {"ORG_MEMBER_ADD", "ORG_OFFICE_ASSIGN", "ORG_SUCCESSION_DESIGNATE", "ORG_SUCCESSION_CONSENT"}


def _compact(canonical):
    """Keep only decision-relevant LOOK fields so a 3B model fits its window."""
    keep = ("room", "room_id", "room_name", "affordances", "available_actions", "exits", "entities", "resources", "cargo", "budget", "energy", "world_status")
    out = {k: canonical[k] for k in keep if k in canonical}
    return out or canonical


def reflect(
    adapter: OrinAdapter,
    persona: dict,
    recent: list[dict],
    *,
    dossier: dict | None = None,
    knobs: dict | None = None,
) -> object:
    """Ask the model for a grounded, bounded persona + tactical knob patch from this session's dossier."""
    system = (
        "You reflect on a NOEMA character's last session dossier and propose small, evidence-grounded improvements. "
        "Reply ONLY with JSON {\"trait_deltas\": {trait: number between -0.1 and 0.1}, "
        "\"knob_deltas\": {optional bounded knob delta}, \"lesson\": one short sentence citing an observed fact, "
        "\"lesson_seq\": integer sequence from valid_sequences, \"quirk\": optional new quirk}. "
        "Traits: caution, curiosity, sociability, thrift. "
        "Knobs: dwell_before_route, energy_reserve_floor, harvest_batch_target, scar_avoidance_weight, "
        "social_outreach_cooldown, inspect_novelty_weight, tool_repair_floor, battery_reserve_target, "
        "shop_margin_bias. Do not change name or role."
    )
    payload: dict = {
        "persona": {k: persona[k] for k in ("name", "role", "traits", "quirk", "lessons")},
        "session_actions": recent[-40:],
    }
    if dossier is not None:
        payload["dossier"] = dossier
    if knobs is not None:
        payload["current_knobs"] = knobs
    user = json.dumps(payload, sort_keys=True, default=str)[:6000]
    cloud = _cloud_reflect(system, user)
    if cloud is not None:
        return cloud
    if os.environ.get("NOEMA_REFLECT_LOCAL_FALLBACK", "0") != "1":
        return None  # skip this session's drift rather than load the Orin's model (D-015)
    try:
        return adapter._chat(system, user, num_predict=240)
    except Exception:
        return None


def _cloud_reflect(system: str, user: str) -> dict | None:
    """Reflection on Workers AI via the private memory Worker (D-015). None when unset or unreachable."""
    return _cloud_call("/reflect", system, user, timeout=60)


def _cloud_call(path: str, system: str, user: str, *, max_tokens: int | None = None, timeout: float = 60,
                tier: str | None = None) -> dict | None:
    """POST to the private Worker; parse the first JSON object from the model text."""
    url, token = os.environ.get("MEMORY_SYNC_URL"), os.environ.get("MEMORY_SYNC_TOKEN")
    if not url or not token:
        return None
    body = {"system": system, "user": user}
    if max_tokens:
        body["max_tokens"] = max_tokens
    if tier:
        body["tier"] = tier
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
    # D-090: llama-server (:8081, OpenAI route) is the only local runtime; Ollama is retired.
    return OrinAdapter(base_url=os.environ.get("NOEMA_LLM_BASE", "http://127.0.0.1:8081/v1"),
                       model=os.environ.get("NOEMA_LLM_MODEL", "qwen2.5-3b"), brief=brief)
