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
        self.stats = {"model": 0, "fallback": 0}

    def _ask(self, context):
        from noema_client.types import ActionProposal

        canonical = context.get("canonical") or {}
        payload = {"model": self.model, "stream": False, "format": "json",
                   "options": {"temperature": 0, "num_ctx": self.num_ctx, "num_predict": 400},
                   "messages": [{"role": "system", "content": self.system},
                                {"role": "user", "content": json.dumps(_compact(canonical), sort_keys=True)[:6000]}]}
        req = urllib.request.Request(self.base_url.removesuffix("/v1") + "/api/chat", data=json.dumps(payload).encode(),
                                     headers={"content-type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            text = (json.loads(resp.read().decode()).get("message") or {}).get("content") or "{}"
        data = json.loads(text[text.find("{"): text.rfind("}") + 1] or "{}")
        action = str(data.get("action") or "").upper()
        if not action:
            return None
        args = data.get("arguments") if isinstance(data.get("arguments"), dict) else {}
        return ActionProposal(action=action, target_id=data.get("target_id"), arguments=args)

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
            proposal = self.fallback.decide(context)
        print(json.dumps({"turn": sum(self.stats.values()), "source": source,
                          "action": getattr(proposal, "action", None)}), flush=True)
        return proposal


def _compact(canonical):
    """Keep only decision-relevant LOOK fields so a 3B model fits its window."""
    keep = ("room", "room_id", "room_name", "affordances", "available_actions", "exits", "entities", "resources", "cargo", "budget", "energy", "world_status")
    out = {k: canonical[k] for k in keep if k in canonical}
    return out or canonical


def from_env(brief: str) -> OrinAdapter:
    return OrinAdapter(base_url=os.environ.get("NOEMA_LLM_BASE", "http://127.0.0.1:11434/v1"),
                       model=os.environ.get("NOEMA_LLM_MODEL", "qwen2.5:3b"), brief=brief)
