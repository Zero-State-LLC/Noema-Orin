"""Hardened 4-stage Recursive Self-Improvement (RSI) ratchet and persistent mind state.

Separates immutable safety/role constitution from evolvable character (`persona.json`)
and bounded tactical knobs (`policy_knobs.json`). Every mutation is validated against
hard invariants, evaluated over a multi-session canary window using deterministic
fitness metrics, and automatically rolled back + quarantined on regression.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

# Deep Time fossilization horizon in NOEMA (deep-time.ts: 40 cycles).
DEEP_TIME_EPOCH_CYCLES = 40

# Canary evaluation window and rollback thresholds.
CANARY_WINDOW_SESSIONS = 3
REGRESSION_TOLERANCE = 0.08
MAX_REJECTION_RATE = 0.15
MAX_ZERO_ENERGY_STREAK = 10

# Strictly bounded tactical knobs per role: (default, min, max, is_int).
KNOB_SPECS: dict[str, tuple[float, float, float, bool]] = {
    "dwell_before_route": (2, 1, 4, True),
    "energy_reserve_floor": (2, 1, 5, True),
    "harvest_batch_target": (8, 3, 8, True),
    "scar_avoidance_weight": (0.7, 0.0, 1.0, False),
    "social_outreach_cooldown": (12, 6, 30, True),
    "inspect_novelty_weight": (0.6, 0.0, 1.0, False),
}


def atomic_write_text(path: Path, text: str, *, mode: int = 0o600) -> None:
    """Crash-safe atomic file replacement in the target directory."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def atomic_write_json(path: Path, data: Any, *, mode: int = 0o600) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True), mode=mode)


def default_knobs(traits: dict[str, float] | None = None) -> dict[str, float | int]:
    """Initialize bounded tactical knobs, lightly seeded from persona traits."""
    knobs: dict[str, float | int] = {k: (int(v[0]) if v[3] else float(v[0])) for k, v in KNOB_SPECS.items()}
    if not isinstance(traits, dict):
        return knobs
    caution = float(traits.get("caution", 0.5))
    thrift = float(traits.get("thrift", 0.5))
    curiosity = float(traits.get("curiosity", 0.5))
    sociability = float(traits.get("sociability", 0.5))
    knobs["energy_reserve_floor"] = int(max(1, min(5, round(1 + caution * 3))))
    knobs["harvest_batch_target"] = int(max(3, min(8, round(4 + thrift * 4))))
    knobs["inspect_novelty_weight"] = round(max(0.0, min(1.0, 0.25 + curiosity * 0.65)), 3)
    knobs["social_outreach_cooldown"] = int(max(6, min(30, round(24 - sociability * 14))))
    return knobs


def load_or_init_knobs(mind: Path, traits: dict[str, float] | None = None) -> dict[str, float | int]:
    path = mind / "policy_knobs.json"
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return clamp_knobs(raw, traits)
        except (ValueError, OSError):
            pass
    knobs = default_knobs(traits)
    atomic_write_json(path, knobs)
    return knobs


def clamp_knobs(raw: dict[str, Any], traits: dict[str, float] | None = None) -> dict[str, float | int]:
    base = default_knobs(traits)
    out: dict[str, float | int] = {}
    for k, (_default, lo, hi, is_int) in KNOB_SPECS.items():
        val = raw.get(k, base[k])
        if type(val) not in (int, float):
            val = base[k]
        clamped = max(lo, min(hi, float(val)))
        out[k] = int(round(clamped)) if is_int else round(clamped, 3)
    return out


def apply_knob_deltas(
    current: dict[str, float | int], deltas: object
) -> tuple[dict[str, float | int], bool]:
    """Apply bounded tactical knob deltas. Unknown keys or invalid types fail closed."""
    if not deltas:
        return dict(current), True
    if type(deltas) is not dict or set(deltas) - set(KNOB_SPECS):
        return dict(current), False
    nxt = dict(current)
    for k, raw in deltas.items():
        if type(raw) not in (int, float):
            return dict(current), False
        _default, lo, hi, is_int = KNOB_SPECS[k]
        max_step = 1.0 if is_int else 0.15
        step = max(-max_step, min(max_step, float(raw)))
        val = max(lo, min(hi, float(nxt.get(k, _default)) + step))
        nxt[k] = int(round(val)) if is_int else round(val, 3)
    return nxt, True


def load_agenda(mind: Path) -> dict[str, Any]:
    """Load persistent medium-loop agenda surviving 30-min session restarts."""
    path = mind / "agenda.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (ValueError, OSError):
            pass
    return {"held_track": None, "build_room": None, "epoch": 0, "steps": [], "updated_seq": 0}


def save_agenda(mind: Path, agenda: dict[str, Any]) -> None:
    clean = {
        "held_track": agenda.get("held_track"),
        "build_room": agenda.get("build_room"),
        "epoch": int(agenda.get("epoch") or 0),
        "steps": list(agenda.get("steps") or [])[:5],
        "updated_seq": int(agenda.get("updated_seq") or 0),
    }
    atomic_write_json(mind / "agenda.json", clean)


def build_session_dossier(
    *,
    role: str,
    role_verbs: set[str],
    turn_log: list[dict[str, Any]],
    rejections: dict[str, Any] | None = None,
    stop_reason: str | None = None,
    loop_breaks: int = 0,
    deep_time_seen: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structured, grounded dossier fed into reflect() and fitness evaluation."""
    total = len(turn_log)
    role_hits = sum(1 for t in turn_log if str(t.get("action") or "").upper() in role_verbs)
    idle_hits = sum(1 for t in turn_log if str(t.get("action") or "").upper() in {"LOOK", "WAIT", "INSPECT", "MOVE"})
    rej_map = (rejections or {}).get("by_verb_code") if isinstance(rejections, dict) else {}
    rej_total = sum(int(v) for v in (rej_map or {}).values() if isinstance(v, (int, float)))
    rooms = sorted({str(t.get("room")) for t in turn_log if t.get("room")})
    seqs = sorted({int(t["seq"]) for t in turn_log if isinstance(t.get("seq"), int) and t["seq"] > 0})
    zero_streak = 0
    for t in reversed(turn_log):
        if (t.get("budgets") or {}).get("energy") == 0:
            zero_streak += 1
        else:
            break
    social_count = sum(
        1 for t in turn_log if str(t.get("action") or "").upper() in {"MESSAGE", "SHOUT", "BOARD", "ORG_OFFICE_ACT", "ATTEST"}
    )
    impact_events = sum(
        1
        for t in turn_log
        if str(t.get("action") or "").upper()
        in {"REPAIR", "RESTORE", "UPGRADE", "CONSTRUCT", "SUPPLY", "RECONSTRUCT", "RECONSTRUCT_PUBLISH",
            "RECONSTRUCT_SUPERSEDE", "ATTEST", "ORG_OFFICE_ACT", "ORG_GOVERNANCE_RULE", "CONNECT", "BOARD", "SHOUT"}
    )
    recent_turns = [
        {
            "seq": t.get("seq"),
            "room": t.get("room"),
            "action": t.get("action"),
            "target": t.get("target"),
            "source": t.get("source"),
            "energy": (t.get("budgets") or {}).get("energy"),
            "consequence": str(t.get("consequence") or "")[:120],
        }
        for t in turn_log[-25:]
    ]
    return {
        "role": role,
        "turns": total,
        "role_action_rate": round(role_hits / total, 4) if total else 0.0,
        "idle_rate": round(idle_hits / total, 4) if total else 0.0,
        "rejection_rate": round(min(1.0, rej_total / total), 4) if total else 0.0,
        "rejection_count": rej_total,
        "rejections_by_code": dict(rej_map or {}),
        "loop_break_rate": round(min(1.0, loop_breaks / total), 4) if total else 0.0,
        "zero_energy_streak": zero_streak,
        "unique_rooms": len(rooms),
        "social_events": social_count,
        "impact_rate": round(min(1.0, (impact_events + len(rooms) * 0.25) / max(1, total)), 4) if total else 0.0,
        "stop_reason": stop_reason,
        "valid_sequences": seqs,
        "deep_time": deep_time_seen or {},
        "recent_turns": recent_turns,
    }


def compute_fitness(dossier: dict[str, Any]) -> float:
    """Deterministic per-session composite fitness score in [0, 1]."""
    if int(dossier.get("turns") or 0) <= 0:
        return 0.0
    role_rate = max(0.0, min(1.0, float(dossier.get("role_action_rate") or 0.0)))
    rej_rate = max(0.0, min(1.0, float(dossier.get("rejection_rate") or 0.0)))
    loop_rate = max(0.0, min(1.0, float(dossier.get("loop_break_rate") or 0.0)))
    impact = max(0.0, min(1.0, float(dossier.get("impact_rate") or 0.0)))
    score = 0.40 * role_rate + 0.25 * (1.0 - rej_rate) + 0.20 * (1.0 - loop_rate) + 0.15 * impact
    return round(max(0.0, min(1.0, score)), 4)


def mutation_signature(patch: dict[str, Any]) -> str:
    canonical = json.dumps(patch, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class RsiRatchet:
    """Persistent 4-stage RSI fitness gate with automatic rollback and quarantine."""

    def __init__(self, mind: Path) -> None:
        self.mind = mind
        self.state_path = mind / "rsi_state.json"
        self.quarantine_path = mind / "quarantine.jsonl"
        self.state = self._load()

    def _load(self) -> dict[str, Any]:
        if self.state_path.is_file():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except (ValueError, OSError):
                pass
        return {
            "baseline_fitness": None,
            "baseline_samples": [],
            "last_good_persona_version": 1,
            "last_good_knobs": None,
            "candidate": None,
            "last_epoch": 0,
            "rollbacks": 0,
            "promotions": 0,
        }

    def save(self) -> None:
        atomic_write_json(self.state_path, self.state)

    def quarantined_signatures(self) -> set[str]:
        if not self.quarantine_path.is_file():
            return set()
        out: set[str] = set()
        for line in self.quarantine_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                row = json.loads(line)
                if isinstance(row, dict) and row.get("signature"):
                    out.add(str(row["signature"]))
            except ValueError:
                continue
        return out

    def _record_quarantine(self, signature: str, reason: str, patch: dict[str, Any], fitness: float) -> None:
        self.mind.mkdir(mode=0o700, parents=True, exist_ok=True)
        entry = json.dumps({"signature": signature, "reason": reason, "fitness": fitness, "patch": patch}, sort_keys=True)
        with self.quarantine_path.open("a", encoding="utf-8") as fh:
            fh.write(entry + "\n")

    def evaluate_session(
        self,
        dossier: dict[str, Any],
        persona: dict[str, Any],
        knobs: dict[str, float | int],
    ) -> dict[str, Any]:
        """Evaluate current session against active canary or baseline.

        Returns {verdict: 'BASELINE'|'CANARY_HOLD'|'PROMOTED'|'ROLLED_BACK', fitness, rollback_persona_version?, rollback_knobs?}.
        """
        fitness = compute_fitness(dossier)
        zero_streak = int(dossier.get("zero_energy_streak") or 0)
        rej_rate = float(dossier.get("rejection_rate") or 0.0)
        cand = self.state.get("candidate")

        if cand is None:
            samples = (list(self.state.get("baseline_samples") or []) + [fitness])[-CANARY_WINDOW_SESSIONS:]
            self.state["baseline_samples"] = samples
            self.state["baseline_fitness"] = round(sum(samples) / len(samples), 4)
            self.state["last_good_persona_version"] = int(persona.get("version") or 1)
            self.state["last_good_knobs"] = dict(knobs)
            self.save()
            return {"verdict": "BASELINE", "fitness": fitness, "baseline": self.state["baseline_fitness"]}

        cand_scores = list(cand.get("scores") or []) + [fitness]
        cand["scores"] = cand_scores
        baseline = float(self.state.get("baseline_fitness") or 0.0)
        hard_fail = zero_streak >= MAX_ZERO_ENERGY_STREAK or rej_rate > MAX_REJECTION_RATE
        mean_cand = round(sum(cand_scores) / len(cand_scores), 4)

        if hard_fail or (len(cand_scores) >= CANARY_WINDOW_SESSIONS and mean_cand < baseline - REGRESSION_TOLERANCE):
            reason = (
                f"zero_energy_streak={zero_streak}"
                if zero_streak >= MAX_ZERO_ENERGY_STREAK
                else f"rejection_rate={rej_rate}"
                if rej_rate > MAX_REJECTION_RATE
                else f"fitness_regression({mean_cand}<{round(baseline - REGRESSION_TOLERANCE, 4)})"
            )
            self._record_quarantine(str(cand.get("signature") or ""), reason, cand.get("patch") or {}, mean_cand)
            rollback_ver = int(self.state.get("last_good_persona_version") or 1)
            rollback_knobs = dict(self.state.get("last_good_knobs") or knobs)
            self.state["candidate"] = None
            self.state["rollbacks"] = int(self.state.get("rollbacks") or 0) + 1
            self.save()
            return {
                "verdict": "ROLLED_BACK",
                "reason": reason,
                "fitness": mean_cand,
                "baseline": baseline,
                "rollback_persona_version": rollback_ver,
                "rollback_knobs": rollback_knobs,
            }

        if len(cand_scores) >= CANARY_WINDOW_SESSIONS:
            self.state["baseline_samples"] = cand_scores[-CANARY_WINDOW_SESSIONS:]
            self.state["baseline_fitness"] = mean_cand
            self.state["last_good_persona_version"] = int(persona.get("version") or 1)
            self.state["last_good_knobs"] = dict(knobs)
            self.state["candidate"] = None
            self.state["promotions"] = int(self.state.get("promotions") or 0) + 1
            self.save()
            return {"verdict": "PROMOTED", "fitness": mean_cand, "baseline": mean_cand}

        self.state["candidate"] = cand
        self.save()
        return {
            "verdict": "CANARY_HOLD",
            "fitness": fitness,
            "window": f"{len(cand_scores)}/{CANARY_WINDOW_SESSIONS}",
            "baseline": baseline,
        }

    def can_propose(self) -> bool:
        """Cooldown: never stack a second mutation while a canary is still open."""
        return self.state.get("candidate") is None

    def register_candidate(self, patch: dict[str, Any], persona_version: int) -> tuple[bool, str]:
        sig = mutation_signature(patch)
        if sig in self.quarantined_signatures():
            return False, "quarantined"
        if not self.can_propose():
            return False, "canary_active"
        self.state["candidate"] = {
            "signature": sig,
            "patch": patch,
            "persona_version": persona_version,
            "scores": [],
        }
        self.save()
        return True, sig


def replay_verify(
    adapter_factory: Callable[[], Any],
    snapshots: list[dict[str, Any]],
    *,
    denied_verbs: set[str],
    hidden_verbs: set[str] | None = None,
) -> dict[str, Any]:
    """Deterministic offline replay gate before promoting a tactical/persona change."""
    adapter = adapter_factory()
    hidden = set(hidden_verbs or ())
    violations: list[str] = []
    actions: list[str] = []
    for idx, snap in enumerate(snapshots):
        prop = adapter.decide({"canonical": snap})
        act = str(getattr(prop, "action", "") or "").upper()
        actions.append(act)
        if act in denied_verbs:
            violations.append(f"turn {idx}: denied verb {act}")
        if not act:
            violations.append(f"turn {idx}: empty action")
    return {
        "ok": len(violations) == 0 and len(actions) == len(snapshots),
        "turns": len(actions),
        "distinct_actions": len(set(actions)),
        "violations": violations,
        "actions": actions,
    }
