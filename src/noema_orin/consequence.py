"""Controller-local consequence model: a table of counts fitted from transition rows (C2, #197).

Stage 1 estimator of Spec #194 (D-080). For a canonical observation and one candidate command it
estimates whether the command is rejected, how each budget changes, and whether the room changes.

Boundaries:
- An approximation fitted from this Controller's own turns. The hosted reducers remain the only world
  truth; every estimate here is INFERRED, private (ADR-0002) and never placed on the wire.
- Pure standard library, no model server. A prediction is a few dictionary lookups.
- The context key reads only: the action, whether its affordance is advertised as available, whether
  the affordance's stated requirements are met, an energy bucket, the room id, and whether the target
  is in the room. It never reads message text, world text, or anything about another Player.
- A quantity without enough rows behind it is NOT_COMPUTABLE, never a default.

Keys back off from specific to coarse, so a command seen in other rooms still gets an estimate in a
new one. `basis` names the most specific key that carried any part of the prediction.
"""

from __future__ import annotations

from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any, Iterable, Mapping

NOT_COMPUTABLE = "NOT_COMPUTABLE"
BUDGETS = ("energy", "attention", "compute", "storage", "influence")
LEVELS = ("action+budget+room", "action+budget", "action")
ENERGY_BUCKETS = ((0, "0"), (2, "1-2"), (5, "3-5"))  # upper bound inclusive; above the last is "6+"
MAX_DISTINCT_DELTAS = 64

DEFAULT_MIN_SUPPORT = 5  # placeholder: the production value comes from measured rows (C5, #200)
DEFAULT_MAX_KEYS = 2048


def _number(value: Any) -> float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _action_of(option: Any) -> tuple[str, Any]:
    if isinstance(option, Mapping):
        return str(option.get("action") or "").upper(), option.get("target_id")
    return str(getattr(option, "action", "") or "").upper(), getattr(option, "target_id", None)


def _energy_bucket(resources: Mapping[str, Any]) -> str:
    energy = _number(resources.get("energy"))
    if energy is None:
        return "?"
    for upper, name in ENERGY_BUCKETS:
        if energy <= upper:
            return name
    return "6+"


def _affordance(canonical: Mapping[str, Any], action: str, target_id: Any) -> Mapping[str, Any] | None:
    """The advertised affordance for this command: an exact target match first, else one with no target."""
    untargeted = None
    affordances = canonical.get("affordances")
    for aff in affordances if isinstance(affordances, list) else []:
        if not isinstance(aff, Mapping):
            continue
        names = {str(aff.get(k) or "").upper() for k in ("action", "verb", "operation")}
        if action not in names:
            continue
        target = aff.get("target_id") or aff.get("target")
        if target_id is not None and target == target_id:
            return aff
        if target is None and untargeted is None:
            untargeted = aff
    return untargeted


def features(canonical: Mapping[str, Any], action: str, target_id: Any) -> tuple:
    """The most specific context key. Coarser keys are prefixes of it (see `_keys`)."""
    canonical = _mapping(canonical)
    action = str(action or "").upper()
    resources = _mapping(canonical.get("resources"))
    location = _mapping(canonical.get("location"))
    aff = _affordance(canonical, action, target_id)
    if aff is None:
        advertised, required = "unadvertised", "?"
    else:
        advertised = "unavailable" if aff.get("available") is False else "available"
        requires = _mapping(aff.get("requires"))
        if not requires:
            required = "none"
        else:
            have = [(_number(resources.get(k)), _number(v)) for k, v in requires.items()]
            required = "?" if any(a is None or b is None for a, b in have) else ("met" if all(a >= b for a, b in have) else "unmet")
    if target_id is None:
        target_here = "none"
    else:
        entities = location.get("entities")
        here = {e.get("entity_id") for e in (entities if isinstance(entities, list) else []) if isinstance(e, Mapping)}
        target_here = "here" if target_id in here else "elsewhere"
    return (action, advertised, required, _energy_bucket(resources), str(location.get("room_id") or "?"), target_here)


def _keys(full: tuple) -> tuple[tuple, tuple, tuple]:
    return full, full[:4], full[:2]


class _Stats:
    __slots__ = ("labelled", "rejected", "followed", "moved", "deltas")

    def __init__(self) -> None:
        self.labelled = 0  # rows with a recorded outcome
        self.rejected = 0
        self.followed = 0  # rows with a next observation
        self.moved = 0
        self.deltas: dict[str, Counter] = {}


def _median(counts: Counter) -> float | int:
    total = sum(counts.values())
    seen = 0
    for value in sorted(counts):
        seen += counts[value]
        if seen * 2 >= total:
            return int(value) if float(value).is_integer() else value
    return 0


class ConsequenceModel:
    def __init__(self, *, min_support: int = DEFAULT_MIN_SUPPORT, max_keys: int = DEFAULT_MAX_KEYS) -> None:
        self.min_support = max(1, int(min_support))
        self.max_keys = max(len(LEVELS), int(max_keys))
        self._table: OrderedDict[tuple, _Stats] = OrderedDict()

    @property
    def key_count(self) -> int:
        return len(self._table)

    @classmethod
    def fit(cls, rows: Iterable[tuple], **kwargs: Any) -> "ConsequenceModel":
        """`rows` yields (observation, action, next_observation or None, outcome or None)."""
        model = cls(**kwargs)
        for obs, action, next_obs, outcome in rows:
            model.observe(obs, action, next_obs, outcome)
        return model

    @classmethod
    def fit_from_log(cls, mind: Path, **kwargs: Any) -> "ConsequenceModel":
        from .transitions import iter_labelled

        try:
            return cls.fit(iter_labelled(mind), **kwargs)
        except OSError:  # no log directory yet
            return cls(**kwargs)

    def observe(self, obs: Any, action: Any, next_obs: Any = None, outcome: Any = None) -> None:
        name, target_id = _action_of(action)
        if not name:
            return
        obs = _mapping(obs)
        ok = _mapping(outcome).get("ok")
        before = _mapping(obs.get("resources"))
        after = _mapping(_mapping(next_obs).get("resources")) if isinstance(next_obs, Mapping) else None
        deltas = {}
        if after is not None:
            for budget in BUDGETS:
                a, b = _number(before.get(budget)), _number(after.get(budget))
                if a is not None and b is not None:
                    deltas[budget] = round(b - a, 2)
            room_before = _mapping(obs.get("location")).get("room_id")
            room_after = _mapping(_mapping(next_obs).get("location")).get("room_id")
        # Most specific first, so the coarse keys are touched last and are the last to be evicted.
        for level, key in enumerate(_keys(features(obs, name, target_id))):
            stats = self._table.get((level, key))
            if stats is None:
                stats = self._table[(level, key)] = _Stats()
            self._table.move_to_end((level, key))
            if ok is True or ok is False:
                stats.labelled += 1
                stats.rejected += 0 if ok else 1
            if after is not None:
                stats.followed += 1
                stats.moved += 1 if (room_before is not None and room_after is not None and room_before != room_after) else 0
                for budget, delta in deltas.items():
                    counts = stats.deltas.setdefault(budget, Counter())
                    if delta in counts or len(counts) < MAX_DISTINCT_DELTAS:
                        counts[delta] += 1
        while len(self._table) > self.max_keys:
            self._table.popitem(last=False)

    def predict(self, canonical: Any, option: Any) -> dict:
        name, target_id = _action_of(option)
        out = {"label": NOT_COMPUTABLE, "basis": None, "support": 0,
               "rejected_p": NOT_COMPUTABLE, "budget_delta": NOT_COMPUTABLE, "room_changes_p": NOT_COMPUTABLE}
        if not name:
            return out
        found = [self._table.get((level, key)) for level, key in enumerate(_keys(features(_mapping(canonical), name, target_id)))]
        used = []
        for level, stats in enumerate(found):
            if stats is not None and stats.labelled >= self.min_support:
                out["rejected_p"] = round((stats.rejected + 1) / (stats.labelled + 2), 4)
                used.append((level, stats.labelled))
                break
        for level, stats in enumerate(found):
            if stats is not None and stats.followed >= self.min_support:
                out["budget_delta"] = {budget: _median(counts) for budget, counts in sorted(stats.deltas.items())}
                out["room_changes_p"] = round((stats.moved + 1) / (stats.followed + 2), 4)
                used.append((level, stats.followed))
                break
        if used:
            level, support = min(used)
            out.update(label="INFERRED", basis=LEVELS[level], support=support)
        return out
