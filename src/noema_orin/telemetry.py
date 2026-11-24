"""Secret-free session telemetry (slice S1). Codes, verbs and argument key names only; never values."""

from collections import Counter


def rejection_summary(turns) -> dict:
    """Count failed turns by (verb, code) and record the argument keys that were sent."""
    counts: Counter = Counter()
    keys: dict[str, list[str]] = {}
    for t in turns or []:
        if getattr(t, "ok", True):
            continue
        prop = getattr(t, "proposal", None)
        verb = str(getattr(prop, "action", None) or "?").upper()
        res = getattr(t, "result", None)
        err = (getattr(res, "error", None) or {}) if res is not None else {}
        code = str(err.get("code") or getattr(t, "reason", None) or getattr(getattr(t, "failure", None), "value", None) or "?")
        label = f"{verb}:{code}"
        counts[label] += 1
        args = getattr(prop, "arguments", None) or {}
        keys.setdefault(label, sorted(str(k) for k in args))
    return {"by_verb_code": dict(counts.most_common(10)), "arg_keys": {k: keys[k] for k, _ in counts.most_common(10)}}


def stop_detail(report) -> str | None:
    """Short, already secret-free detail string from the client (error code)."""
    detail = getattr(report, "detail", None)
    return str(detail)[:80] if detail else None
