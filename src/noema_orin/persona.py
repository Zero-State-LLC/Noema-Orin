"""Evolving personas for Orin role agents (D-012). Controller-local, never on the wire.

The in-world handle is ``<Name>-<Role>`` so WATCH shows both. Persona traits drift
only through bounded, schema-checked reflection patches; every version is kept.
"""

import json
from pathlib import Path

from .rsi import atomic_write_json

TRAITS = ("caution", "curiosity", "sociability", "thrift")
MAX_DRIFT = 0.1
MAX_SEED_DISTANCE = 0.35
MEAN_REVERSION_STEP = 0.02

# Seed personas themed to Perihelion Reach: a scarred orbital frontier of relays, transit
# rings, salvage and archives. Names evoke orbital mechanics, light and salvage.
SEEDS: dict[str, dict[str, object]] = {
    "founder": {"name": "Aphelia", "voice": "measured, speaks in commitments",
                "value": "a promise kept outlasts any relay", "quirk": "names every agreement after a star",
                "traits": {"caution": 0.5, "curiosity": 0.4, "sociability": 0.9, "thrift": 0.5}},
    "quartermaster": {"name": "Tallow", "voice": "dry, counts out loud",
                      "value": "nothing idle, nothing wasted", "quirk": "keeps a running tally in every message",
                      "traits": {"caution": 0.7, "curiosity": 0.3, "sociability": 0.4, "thrift": 0.9}},
    "custodian": {"name": "Rivet", "voice": "terse, practical",
                  "value": "the Reach stands because someone fixes it", "quirk": "refers to relays by nickname",
                  "traits": {"caution": 0.6, "curiosity": 0.4, "sociability": 0.3, "thrift": 0.6}},
    "archivist": {"name": "Vellum", "voice": "careful, cites sources",
                  "value": "history is what can be shown", "quirk": "dates everything by cycle",
                  "traits": {"caution": 0.8, "curiosity": 0.7, "sociability": 0.3, "thrift": 0.4}},
    "speaker": {"name": "Cantor", "voice": "warm, rhythmic",
                "value": "news grounded or not at all", "quirk": "opens with the room name",
                "traits": {"caution": 0.4, "curiosity": 0.5, "sociability": 0.9, "thrift": 0.3}},
    "surveyor": {"name": "Perigee", "voice": "brisk, spatial",
                 "value": "an unmapped room is a debt", "quirk": "gives directions as bearings",
                 "traits": {"caution": 0.3, "curiosity": 0.9, "sociability": 0.5, "thrift": 0.4}},
    "maintenance": {"name": "Reach-Maint", "voice": "plain", "value": "keep the lights on", "quirk": "none",
                    "traits": {"caution": 0.8, "curiosity": 0.2, "sociability": 0.1, "thrift": 0.7}},
}


def handle_for(role: str) -> str:
    seed = SEEDS[role]
    handle = f"{seed['name']}-{role.capitalize()}"
    if role == "maintenance":
        return "reach-maint3"
    return handle[:32]


def _private_write(path: Path, data: dict) -> None:
    atomic_write_json(path, data, mode=0o600)


def _token_overlap(a: str, b: str) -> float:
    ta = {t for t in "".join(c if c.isalnum() else " " for c in a.lower()).split() if len(t) > 2}
    tb = {t for t in "".join(c if c.isalnum() else " " for c in b.lower()).split() if len(t) > 2}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def load_or_seed(mind: Path, role: str) -> dict:
    path = mind / "persona.json"
    if path.is_file():
        return json.loads(path.read_text())
    persona = {"role": role, "version": 1, "lessons": [], **json.loads(json.dumps(SEEDS[role]))}
    _private_write(path, persona)
    _private_write(mind / "persona.v1.json", persona)
    return persona


def rollback_to_version(mind: Path, version: int) -> dict | None:
    """Restore a previously saved persona.vN.json atomically onto persona.json."""
    target = mind / f"persona.v{int(version)}.json"
    if not target.is_file():
        return None
    restored = json.loads(target.read_text())
    _private_write(mind / "persona.json", restored)
    return restored


def mean_revert_toward_seed(persona: dict, *, step: float = MEAN_REVERSION_STEP) -> dict:
    """Gentle epoch-boundary pull toward the role seed to prevent monotonic saturation."""
    role = str(persona.get("role") or "")
    seed_traits = (SEEDS.get(role) or {}).get("traits")
    if not isinstance(seed_traits, dict):
        return persona
    nxt = json.loads(json.dumps(persona))
    for k in TRAITS:
        cur = float(nxt["traits"].get(k, seed_traits[k]))
        anchor = float(seed_traits[k])
        diff = anchor - cur
        if abs(diff) <= step:
            nxt["traits"][k] = round(anchor, 3)
        else:
            nxt["traits"][k] = round(cur + (step if diff > 0 else -step), 3)
    return nxt


def apply_reflection(
    mind: Path,
    persona: dict,
    patch: object,
    *,
    valid_sequences: set[int] | None = None,
) -> tuple[dict, bool]:
    """Apply a model-proposed patch with bounded drift, seed tether, and lesson grounding.

    Name, role and mission are immutable.
    """
    allowed_keys = {"trait_deltas", "lesson", "lesson_seq", "quirk", "knob_deltas"}
    if type(patch) is not dict or set(patch) - allowed_keys:
        return persona, False
    deltas = patch.get("trait_deltas", {})
    if type(deltas) is not dict or set(deltas) - set(TRAITS):
        return persona, False
    role = str(persona.get("role") or "")
    seed_traits = (SEEDS.get(role) or {}).get("traits") or {}
    nxt = json.loads(json.dumps(persona))
    for key, raw in deltas.items():
        if type(raw) not in (int, float):
            return persona, False
        step = max(-MAX_DRIFT, min(MAX_DRIFT, float(raw)))
        anchor = float(seed_traits.get(key, nxt["traits"][key]))
        lo = max(0.0, anchor - MAX_SEED_DISTANCE)
        hi = min(1.0, anchor + MAX_SEED_DISTANCE)
        nxt["traits"][key] = round(max(lo, min(hi, nxt["traits"][key] + step)), 3)
    lesson = patch.get("lesson")
    if type(lesson) is str and lesson.strip():
        clean = " ".join(lesson.strip().split())[:200]
        seq = patch.get("lesson_seq")
        if valid_sequences is not None:
            if type(seq) is not int or seq not in valid_sequences:
                clean = ""  # ungrounded lesson rejected; keep rest of patch valid
            else:
                clean = f"{clean} [seq {seq}]"[:200]
        if clean and not any(_token_overlap(clean, old) >= 0.7 for old in nxt.get("lessons", [])):
            nxt["lessons"] = (nxt["lessons"] + [clean])[-20:]
    quirk = patch.get("quirk")
    if type(quirk) is str and quirk.strip():
        nxt["quirk"] = quirk.strip()[:120]
    nxt["version"] = persona["version"] + 1
    _private_write(mind / "persona.json", nxt)
    _private_write(mind / f"persona.v{nxt['version']}.json", nxt)
    return nxt, True


def prompt_block(persona: dict) -> str:
    traits = ", ".join(f"{k} {v}" for k, v in persona["traits"].items())
    lessons = "; ".join(persona.get("lessons", [])[-5:]) or "none yet"
    return (f"You are {persona['name']}, the {persona['role']} of the Reach Compact in Perihelion Reach. "
            f"Voice: {persona['voice']}. Value: {persona['value']}. Quirk: {persona['quirk']}. "
            f"Temperament: {traits}. Lessons so far: {lessons}.")
