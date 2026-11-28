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


def _snapshot(obs: Any) -> tuple[dict, Any]:
    """What a turn's before/after comparison needs from an observation: numeric budgets and the room id."""
    obs = _mapping(obs)
    resources = _mapping(obs.get("resources"))
    return ({b: resources[b] for b in BUDGETS if _number(resources.get(b)) is not None},
            _mapping(obs.get("location")).get("room_id"))


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

        newest_segments = kwargs.pop("newest_segments", None)
        try:
            return cls.fit(iter_labelled(mind, newest_segments=newest_segments), **kwargs)
        except OSError:  # no log directory yet
            return cls(**kwargs)

    def observe(self, obs: Any, action: Any, next_obs: Any = None, outcome: Any = None) -> None:
        from .transitions import about_action

        name, target_id = _action_of(action)
        if not name or not about_action(outcome):
            return  # an outage or a lost connection teaches nothing about this action, budgets included
        obs = _mapping(obs)
        self.update(features(obs, name, target_id), _snapshot(obs),
                    _snapshot(next_obs) if isinstance(next_obs, Mapping) else None, _mapping(outcome).get("ok"))

    def update(self, full_key: tuple, before: tuple, after: tuple | None, ok: Any) -> None:
        """Fold in one turn from its context key and `_snapshot`s. `after` is None without a next observation."""
        deltas, moved = {}, False
        if after is not None:
            for budget in BUDGETS:
                a, b = before[0].get(budget), after[0].get(budget)
                if a is not None and b is not None:
                    deltas[budget] = round(b - a, 2)
            moved = before[1] is not None and after[1] is not None and before[1] != after[1]
        # Most specific first, so the coarse keys are touched last and are the last to be evicted.
        for level, key in enumerate(_keys(full_key)):
            stats = self._table.get((level, key))
            if stats is None:
                stats = self._table[(level, key)] = _Stats()
            self._table.move_to_end((level, key))
            if ok is True or ok is False:
                stats.labelled += 1
                stats.rejected += 0 if ok else 1
            if after is not None:
                stats.followed += 1
                stats.moved += 1 if moved else 0
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


# ---- Shadow mode (C3, #198): predict, compare with what happened, report. Behaviour is unchanged. ----

SHADOW_FLAG = "NOEMA_CONSEQUENCE_SHADOW"
STARTUP_SEGMENTS = 4  # at start, fit from the live file and this many newest segments, not the whole log
REJECT_AT = 0.5
MAX_VERBS_REPORTED = 12


def compact(prediction: Mapping[str, Any]) -> Any:
    """The per-turn telemetry form of a prediction: the string NOT_COMPUTABLE, or the estimates."""
    if prediction.get("label") != "INFERRED":
        return NOT_COMPUTABLE
    return {k: prediction[k] for k in ("label", "basis", "support", "rejected_p", "budget_delta", "room_changes_p")}


class ShadowScorer:
    """Holds one session's predictions and scores them once the session's results are known.

    Predictions are made with the model as it stood before the session's own turns were folded in,
    so the score is out of sample. `finish` then folds those turns into the model.
    """

    def __init__(self) -> None:
        self._turns: list[dict] = []

    def reset(self) -> None:
        self._turns = []

    def note(self, canonical: Any, proposal: Any, prediction: Mapping[str, Any]) -> None:
        name, target_id = _action_of(proposal)
        canonical = _mapping(canonical)
        self._turns.append({"action": name, "key": features(canonical, name, target_id),
                            "snapshot": _snapshot(canonical), "prediction": prediction})

    def finish(self, report: Any, model: ConsequenceModel) -> dict | None:
        """Score the session against `report` (what `client.play()` returned, or None after a drop).

        Returns the per-verb summary, or None when there is nothing to score. Always folds the
        session's turns into `model` and resets.
        """
        from .transitions import about_action, decided_results, outcome_of

        turns, self._turns = self._turns, []
        if not turns:
            return None
        outcomes = {turn: outcome_of(result) for turn, result in decided_results([t["action"] for t in turns], report)}
        verbs: dict[str, dict] = {}
        excluded = 0
        for index, turn in enumerate(turns):
            after = turns[index + 1]["snapshot"] if index + 1 < len(turns) else None
            outcome = outcomes.get(index)
            ok = outcome["ok"] if outcome is not None else None
            row = verbs.setdefault(turn["action"], {"turns": 0, "predicted": 0, "tp": 0, "fp": 0, "fn": 0, "tn": 0,
                                                    "budget_scored": 0, "_error": 0.0})
            row["turns"] += 1
            prediction = turn["prediction"]
            if not about_action(outcome):  # the world or the connection failed: neither scored nor learned
                excluded += 1
                row["predicted"] += 1 if prediction.get("label") == "INFERRED" else 0
                continue
            if prediction.get("label") == "INFERRED":
                row["predicted"] += 1
                p = prediction.get("rejected_p")
                if ok is not None and _number(p) is not None:
                    row[("tp" if not ok else "fp") if p >= REJECT_AT else ("fn" if not ok else "tn")] += 1
                expected = prediction.get("budget_delta")
                if after is not None and isinstance(expected, Mapping) and expected:
                    errors = [abs((after[0][b] - turn["snapshot"][0][b]) - delta) for b, delta in expected.items()
                              if b in after[0] and b in turn["snapshot"][0]]
                    if errors:
                        row["budget_scored"] += 1
                        row["_error"] += sum(errors) / len(errors)
            model.update(turn["key"], turn["snapshot"], after, ok)
        if report is None:
            return None
        by_verb = {}
        for verb, row in sorted(verbs.items(), key=lambda item: (-item[1]["turns"], item[0]))[:MAX_VERBS_REPORTED]:
            error = row.pop("_error")
            row["right"], row["wrong"] = row["tp"] + row["tn"], row["fp"] + row["fn"]
            row["budget_mae"] = round(error / row["budget_scored"], 4) if row["budget_scored"] else NOT_COMPUTABLE
            by_verb[verb] = row
        predicted = sum(row["predicted"] for row in verbs.values())
        return {"label": "INFERRED", "turns": len(turns), "no_prediction": len(turns) - predicted,
                "excluded": excluded, "by_verb": by_verb}


def attach_shadow(adapter: Any, mind: Path, env: Mapping[str, str] | None = None) -> bool:
    """Turn shadow mode on for one member. Needs the transition log on and NOEMA_CONSEQUENCE_SHADOW=1."""
    import os

    env = os.environ if env is None else env
    if getattr(adapter, "transition_log", None) is None or str(env.get(SHADOW_FLAG, "0")).strip() != "1":
        return False
    adapter.consequence_model = ConsequenceModel.fit_from_log(mind, newest_segments=STARTUP_SEGMENTS)
    adapter.consequence_scorer = ShadowScorer()
    return True


def close_shadow_session(adapter: Any, report: Any) -> dict | None:
    """Score and fold the session that just ended. Never raises: a failure prints one field."""
    scorer, model = getattr(adapter, "consequence_scorer", None), getattr(adapter, "consequence_model", None)
    if scorer is None or model is None:
        return None
    try:
        return scorer.finish(report, model)
    except Exception as exc:
        import json

        print(json.dumps({"consequence_error": type(exc).__name__}), flush=True)
        scorer.reset()
        return None
