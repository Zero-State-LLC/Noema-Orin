"""Secret-free session telemetry (slice S1). Codes, verbs and argument key names only; never values."""

from collections import Counter
from types import SimpleNamespace

from .transitions import masked_rejection


def _opening_entry(t) -> bool:
    """D-101: noema-client's play() reports the session-opening ENTER_WORLD as the bare CommandResult from act(),
    not as a TurnResult. Only a CommandResult has `idempotency_key`; a TurnResult always has `proposal`, even when
    it is None."""
    return not hasattr(t, "proposal") and hasattr(t, "idempotency_key")


def rejection_summary(turns) -> dict:
    """Count failed turns by (verb, code) and record the argument keys that were sent.

    A turn the client reported ok but the server rejected (noema-client#58) counts as failed too.
    """
    counts: Counter = Counter()
    keys: dict[str, list[str]] = {}
    for t in turns or []:
        if _opening_entry(t):
            # D-101: read as the ENTER_WORLD it stands for. It has no proposal or result of its own, so it was
            # counted as "?:ACTION_REJECTED" and its code (WORLD_INCIDENT in 678 of 681 live sessions) was lost.
            t = SimpleNamespace(ok=getattr(t, "ok", True), reason=None, failure=getattr(t, "failure", None),
                                proposal=SimpleNamespace(action="ENTER_WORLD", arguments={}), result=t)
        masked = masked_rejection(t)
        if getattr(t, "ok", True) and masked is None:
            continue
        prop = getattr(t, "proposal", None)
        verb = str(getattr(prop, "action", None) or "?").upper()
        res = getattr(t, "result", None)
        err = (getattr(res, "error", None) or {}) if res is not None else {}
        code = str(masked or err.get("code") or getattr(t, "reason", None) or getattr(getattr(t, "failure", None), "value", None) or "?")
        label = f"{verb}:{code}"
        counts[label] += 1
        args = getattr(prop, "arguments", None) or {}
        keys.setdefault(label, sorted(str(k) for k in args))
    return {"by_verb_code": dict(counts.most_common(10)), "arg_keys": {k: keys[k] for k, _ in counts.most_common(10)}}


def stop_detail(report) -> str | None:
    """Short, already secret-free detail string from the client (error code)."""
    detail = getattr(report, "detail", None)
    return str(detail)[:80] if detail else None
