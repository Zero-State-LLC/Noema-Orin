"""Grounded character voice synthesis and deterministic fact/seq verifier (T11/#165).

Lets Orin personas speak in-character (`persona.voice`, `value`, `quirk`) strictly from
verified `memory.db` / `shared/map.db` fact tuples while guaranteeing zero hallucinated
sequence citations, zero altered prices/counts, and zero private-state leakage (`ADR-0002`).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from .llm_client import build_voice_schema

MAX_UTTERANCE_CHARS = 280
_SEQ_CITATION_RE = re.compile(r"\bseq\s+(\d+)\b", re.IGNORECASE)
_INT_RE = re.compile(r"\b\d+\b")

# Forbidden Controller-local cognition tokens that must never cross onto the NOEMA wire (ADR-0002).
_PRIVATE_LEAK_TOKENS = (
    "policy_knobs",
    "persona_traits",
    "rsi_state",
    "persona.json",
    "agenda.json",
    "quarantine.jsonl",
    "trait_deltas",
    "knob_deltas",
    "canary_window",
    "sociability",
    "curiosity",
    "caution",
    "thrift",
    "shop_margin_bias",
    "tool_repair_floor",
    "battery_reserve_target",
    "social_outreach_cooldown",
    "inspect_novelty_weight",
)


@dataclass(frozen=True)
class GroundedFact:
    text: str
    seq: int
    room_id: str | None = None
    entity_id: str | None = None
    numbers: tuple[int, ...] = ()


@dataclass(frozen=True)
class FactBundle:
    facts: tuple[GroundedFact, ...]
    fallback_text: str

    @property
    def valid_seqs(self) -> set[int]:
        return {int(f.seq) for f in self.facts if isinstance(f.seq, int) and f.seq > 0}

    @property
    def allowed_numbers(self) -> set[int]:
        nums: set[int] = set(self.valid_seqs)
        for f in self.facts:
            nums.update(int(n) for n in f.numbers)
            for m in _INT_RE.findall(f.text):
                nums.add(int(m))
            for ref in (f.room_id, f.entity_id):
                if ref:
                    for m in _INT_RE.findall(ref):
                        nums.add(int(m))
        return nums


def verify_grounded_utterance(utterance: str, bundle: FactBundle) -> tuple[bool, str]:
    """Deterministic grounding verifier: length, zero private leaks, valid seq citations, exact numbers."""
    text = " ".join(str(utterance or "").split())
    if not text:
        return False, "empty utterance"
    if len(text) > MAX_UTTERANCE_CHARS:
        return False, f"exceeds {MAX_UTTERANCE_CHARS} chars"
    low = text.lower()
    for token in _PRIVATE_LEAK_TOKENS:
        if token in low:
            return False, f"private cognition leak: {token}"

    cited = [int(m.group(1)) for m in _SEQ_CITATION_RE.finditer(text)]
    valid_seqs = bundle.valid_seqs
    if valid_seqs and not cited:
        return False, "missing required seq citation"
    for s in cited:
        if s not in valid_seqs:
            return False, f"ungrounded seq citation: {s}"

    allowed_nums = bundle.allowed_numbers
    stripped_for_nums = _SEQ_CITATION_RE.sub("", text)
    for m in _INT_RE.finditer(stripped_for_nums):
        val = int(m.group(0))
        if val not in allowed_nums:
            return False, f"ungrounded number: {val}"

    return True, "ok"


def synthesize_grounded_utterance(
    persona: dict[str, Any],
    bundle: FactBundle,
    *,
    llm_fn: Callable[[str, str, dict[str, Any]], dict[str, Any] | None] | None = None,
) -> tuple[str, bool]:
    """Synthesize a verified in-character utterance, or deterministically fall back to `bundle.fallback_text`."""
    fallback = str(bundle.fallback_text or "")[:MAX_UTTERANCE_CHARS]
    if llm_fn is None or not bundle.facts:
        return fallback, False

    # Strictly public style fields only — never numeric traits, knobs, lessons, or RSI state.
    style = {
        "name": str(persona.get("name") or "Resident"),
        "role": str(persona.get("role") or "resident"),
        "voice": str(persona.get("voice") or "clear, grounded"),
        "value": str(persona.get("value") or "grounded reports only"),
        "quirk": str(persona.get("quirk") or ""),
    }
    system = (
        f"You are {style['name']} ({style['role']}). Voice: {style['voice']}. "
        f"Value: {style['value']}. Quirk: {style['quirk']}. "
        "Write ONE short in-world statement (<=240 chars) reporting ONLY the provided verified facts. "
        "Include '(observed at seq N)' citing an exact seq from the facts. Do not invent numbers, rooms, or items."
    )
    user = json.dumps(
        {
            "facts": [
                {"text": f.text, "seq": f.seq, "room_id": f.room_id, "entity_id": f.entity_id}
                for f in bundle.facts
            ]
        },
        sort_keys=True,
    )
    schema = build_voice_schema(sorted(bundle.valid_seqs))
    try:
        out = llm_fn(system, user, schema)
    except Exception:
        return fallback, False
    if not isinstance(out, dict):
        return fallback, False
    candidate = " ".join(str(out.get("utterance") or "").split())
    ok, _reason = verify_grounded_utterance(candidate, bundle)
    if not ok:
        return fallback, False
    return candidate, True
