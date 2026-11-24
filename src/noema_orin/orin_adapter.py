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
        self.stats = {"model": 0, "fallback": 0, "loop_break": 0}
        self.recent: list[dict] = []
        self.allowed: frozenset = frozenset()
        self.default_args: dict[str, dict] = {}

    def set_brief(self, brief: str) -> None:
        from noema_client.adapters.openai_compatible import SYSTEM_PROMPT

        self.system = SYSTEM_PROMPT + " Role: " + brief

    def _chat(self, system: str, user: str, num_predict: int = 400) -> dict:
        payload = {"model": self.model, "stream": False, "format": "json",
                   "options": {"temperature": 0.4, "num_ctx": self.num_ctx, "num_predict": num_predict},
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        req = urllib.request.Request(self.base_url.removesuffix("/v1") + "/api/chat", data=json.dumps(payload).encode(),
                                     headers={"content-type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            text = (json.loads(resp.read().decode()).get("message") or {}).get("content") or "{}"
        data = json.loads(text[text.find("{"): text.rfind("}") + 1] or "{}")
        return data if isinstance(data, dict) else {}

    def _ask(self, context):
        from noema_client.types import ActionProposal

        canonical = context.get("canonical") or {}
        recent = [f"{r['action']} {r.get('target') or ''}".strip() for r in self.recent[-5:]]
        options = _options(canonical, self.allowed)
        if not options:
            return None
        user = json.dumps({"recent_own_actions": recent, "room": canonical.get("room_name") or canonical.get("room"),
                           "resources": canonical.get("resources"), "options": options}, sort_keys=True)[:5000]
        instruction = (self.system + " Choose exactly ONE option by its index from `options`. Prefer actions unique to your role. "
                       "Vary your actions; never pick the same option three times in a row. "
                       "Reply ONLY with JSON {\"choice\": <index>, \"why\": \"<6 words>\"}. Do not echo the input.")
        data = self._chat(instruction, user, num_predict=60)
        idx = data.get("choice")
        if type(idx) is not int or not 0 <= idx < len(options):
            return None
        pick = options[idx]
        return ActionProposal(action=pick["action"], target_id=pick.get("target_id"),
                              arguments={**self.default_args.get(pick["action"], {}), **dict(pick.get("arguments") or {})})

    def _role_fallback(self, context):
        """Scripted choice that still honours the role: unique verbs first, then MOVE, then anything allowed."""
        from noema_client.types import ActionProposal

        options = _options(context.get("canonical") or {}, self.allowed)
        tried = {(r["action"], r.get("target")) for r in self.recent[-3:]}
        shared = {"LOOK", "INSPECT", "WAIT", "OBSERVE", "ENTER_WORLD", "LEAVE_WORLD", "MOVE"}
        for tier in (lambda o: o["action"] not in shared, lambda o: o["action"] == "MOVE", lambda o: True):
            for opt in options:
                if tier(opt) and (opt["action"], opt.get("target_id")) not in tried:
                    return ActionProposal(action=opt["action"], target_id=opt.get("target_id"),
                                          arguments={**self.default_args.get(opt["action"], {}), **dict(opt.get("arguments") or {})})
        return self.fallback.decide(context)

    def decide(self, context):
        source = "model"
        try:
            proposal = self._ask(context)
        except Exception:
            proposal = None
        if proposal is not None:
            self.stats["model"] += 1
        else:
            source = "fallback"
            self.stats["fallback"] += 1
            proposal = self._role_fallback(context)
        key = (getattr(proposal, "action", None), getattr(proposal, "target_id", None))
        if len(self.recent) >= 2 and all((r["action"], r.get("target")) == key for r in self.recent[-2:]):
            from noema_client.types import ActionProposal

            source = "loop_break"
            self.stats["loop_break"] += 1
            proposal = ActionProposal(action="MOVE" if key[0] != "MOVE" else "LOOK")
        self.recent = (self.recent + [{"action": getattr(proposal, "action", None),
                                       "target": getattr(proposal, "target_id", None)}])[-40:]
        print(json.dumps({"turn": sum(self.stats.values()), "source": source,
                          "action": getattr(proposal, "action", None)}), flush=True)
        return proposal


def _options(canonical: dict, allowed: frozenset) -> list[dict]:
    """Available advertised affordances this role may use, as a short indexed menu."""
    out = []
    for aff in canonical.get("affordances") or []:
        if not isinstance(aff, dict) or aff.get("available") is False:
            continue
        action = str(aff.get("action") or aff.get("verb") or "").upper()
        if allowed and action not in allowed:
            continue
        args = {k: aff[k] for k in ("operation", "extent", "track", "class", "org_id", "player_id", "dest", "target",
                                    "agreement_type", "scope", "mode", "subject_ref", "claim") if k in aff}
        if isinstance(aff.get("arguments"), dict):
            args.update(aff["arguments"])
        out.append({"i": len(out), "action": action, "label": str(aff.get("label") or "")[:60],
                    "target_id": aff.get("target_id") or aff.get("target"), "arguments": args})
        if len(out) >= 24:
            break
    return out


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
    try:
        return adapter._chat(system, user, num_predict=200)
    except Exception:
        return None


def from_env(brief: str) -> OrinAdapter:
    return OrinAdapter(base_url=os.environ.get("NOEMA_LLM_BASE", "http://127.0.0.1:11434/v1"),
                       model=os.environ.get("NOEMA_LLM_MODEL", "qwen2.5:3b"), brief=brief)
