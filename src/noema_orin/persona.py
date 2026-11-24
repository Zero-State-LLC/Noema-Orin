"""Evolving personas for Orin role agents (D-012). Controller-local, never on the wire.

The in-world handle is ``<Name>-<Role>`` so WATCH shows both. Persona traits drift
only through bounded, schema-checked reflection patches; every version is kept.
"""

import json
import os
from pathlib import Path

TRAITS = ("caution", "curiosity", "sociability", "thrift")
MAX_DRIFT = 0.1

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
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)


def load_or_seed(mind: Path, role: str) -> dict:
    path = mind / "persona.json"
    if path.is_file():
        return json.loads(path.read_text())
    persona = {"role": role, "version": 1, "lessons": [], **json.loads(json.dumps(SEEDS[role]))}
    _private_write(path, persona)
    _private_write(mind / "persona.v1.json", persona)
    return persona


def apply_reflection(mind: Path, persona: dict, patch: object) -> tuple[dict, bool]:
    """Apply a model-proposed patch with bounded drift. Name, role and mission are immutable."""
    if type(patch) is not dict or set(patch) - {"trait_deltas", "lesson", "quirk"}:
        return persona, False
    deltas = patch.get("trait_deltas", {})
    if type(deltas) is not dict or set(deltas) - set(TRAITS):
        return persona, False
    nxt = json.loads(json.dumps(persona))
    for key, raw in deltas.items():
        if type(raw) not in (int, float):
            return persona, False
        step = max(-MAX_DRIFT, min(MAX_DRIFT, float(raw)))
        nxt["traits"][key] = round(max(0.0, min(1.0, nxt["traits"][key] + step)), 3)
    lesson = patch.get("lesson")
    if type(lesson) is str and lesson.strip():
        nxt["lessons"] = (nxt["lessons"] + [lesson.strip()[:200]])[-20:]
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
