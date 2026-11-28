"""Opt-in Controller-local transition log (D-078).

One JSON line per decided turn: the full canonical observation the Controller acted on and the
proposal it returned. The next line of the same session is the resulting observation, so
`iter_transitions` yields (observation, action, next_observation) triples.

When a session ends, `record_outcomes` appends one outcome row per decided turn from the client's own
turn results (accepted, or rejected with its code), and `iter_outcomes` joins them back to the turns.

Boundaries:
- Off unless `NOEMA_TRANSITION_LOG=1`. Merging this code captures nothing.
- Telemetry, not evidence (AGENTS.md): every row is labelled TELEMETRY and nothing here is a claim.
- Controller-local (ADR-0002): files live in the member's private `mind/` directory, mode 0600. They
  are never placed on the NOEMA wire, in model context, or in the cloud memory sync.
- Bounded disk: the live file rotates into gzip segments and the oldest segments are pruned.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Iterator, Mapping

SCHEMA_VERSION = 1
LIVE_NAME = "transitions.jsonl"
_SEGMENT_RE = re.compile(r"^transitions-(\d{6})\.jsonl\.gz$")
# Key names that must never reach disk, whatever depth they appear at. Observations should not carry
# these; this is a backstop for "no tokens or private prompts in telemetry".
_SECRET_KEY_RE = re.compile(r"token|secret|passw|credential|authorization|api[_-]?key|cookie|bearer|prompt", re.IGNORECASE)

OUTCOME_KIND = "outcome"  # rows without a "kind" are turn rows (everything written before C1)
MAX_CODE_CHARS = 80

DEFAULT_MAX_MB = 16
DEFAULT_KEEP = 32

# Client failure classes and server codes that describe the world or the connection, not the proposed
# action: an outage, a pause, a lost connection, or a revision race with another writer. A turn that
# failed this way is logged as it happened, but it is not a verdict on the action (Noema#983).
NOT_ABOUT_ACTION = frozenset({
    "RETRYABLE_TRANSPORT", "AUTH_REQUIRED", "WORLD_NOT_READY", "WORLD_PAUSED", "WORLD_INCIDENT",
    "SETTLEMENT_FAILURE", "SETTLEMENT_RESYNC", "PROTOCOL", "SEAL",
    "INCIDENT", "PAUSED", "NOT_ACTIVE", "STALE_HEAD",
    # D-086: the session is not in the world (ENTER_WORLD failed, usually during an INCIDENT); any verb fails.
    "NOT_IN_WORLD",
})


def outcome_of(result: Any) -> dict:
    """One client turn result as an outcome: `{"ok": True}` or `{"ok": False, "code": ..., "failure": ...}`.

    noema-client 0.2.0 marks a WebSocket ACT_RESULT ok whenever it carries an observation, so a world
    rejection (HTTP 200, body ok=false plus an observation) arrives as ok=True with the error attached
    (noema-client#58). `masked_rejection` recovers the server's verdict from the result itself.
    """
    masked = masked_rejection(result)
    out: dict = {"ok": bool(getattr(result, "ok", False)) and masked is None}
    if masked is not None:
        out["code"] = masked[:MAX_CODE_CHARS]
        out["failure"] = "ACTION_REJECTED"
        return out
    if not out["ok"]:
        error = getattr(getattr(result, "result", None), "error", None) or {}
        failure = getattr(result, "failure", None)
        failure = getattr(failure, "value", failure)
        code = error.get("code") if isinstance(error, Mapping) else None
        out["code"] = str(code or getattr(result, "reason", None) or failure or "?")[:MAX_CODE_CHARS]
        if failure:
            out["failure"] = str(failure)[:MAX_CODE_CHARS]
    return out


def masked_rejection(result: Any) -> str | None:
    """The server's error code when a turn the client reported ok was in fact rejected, else None.

    The CommandResult keeps the error and the raw frame even when its `ok` is wrong, so this reads the
    server's own verdict (`body.ok is False`, or an error code on the result) rather than guessing from
    prose. Once the client honours `body.ok` (noema-client#58) such turns arrive with ok=False and this
    returns None for them.
    """
    if not getattr(result, "ok", False):
        return None
    command = getattr(result, "result", None)
    if command is None:
        return None
    raw = getattr(command, "raw", None)
    if not isinstance(raw, Mapping):
        return None  # only the WebSocket path keeps the frame, and only it masks rejections
    body = raw.get("body") if isinstance(raw.get("body"), Mapping) else {}
    error = getattr(command, "error", None)
    code = str(error.get("code") or "") if isinstance(error, Mapping) else ""
    if "ok" in body:
        return (code or "ACTION_REJECTED") if body.get("ok") is False else None
    return code or None


def about_action(outcome: Any) -> bool:
    """False when a recorded failure was the world's or the connection's, not the action's."""
    if not isinstance(outcome, Mapping) or outcome.get("ok") is not False:
        return True
    return not ({str(outcome.get(k) or "").upper() for k in ("code", "failure")} & NOT_ABOUT_ACTION)


def _scrub(value: Any, dropped: list[int]) -> Any:
    if isinstance(value, Mapping):
        out = {}
        for key, item in value.items():
            if _SECRET_KEY_RE.search(str(key)):
                dropped[0] += 1
                continue
            out[str(key)] = _scrub(item, dropped)
        return out
    if isinstance(value, (list, tuple)):
        return [_scrub(item, dropped) for item in value]
    return value


def _open_private(path: Path, flags: int) -> int:
    return os.open(path, flags | getattr(os, "O_BINARY", 0), 0o600)


class TransitionLog:
    def __init__(self, mind: Path, *, max_bytes: int = DEFAULT_MAX_MB * 1024 * 1024, keep: int = DEFAULT_KEEP) -> None:
        self.mind = Path(mind)
        self.path = self.mind / LIVE_NAME
        self.max_bytes = max(1, int(max_bytes))
        self.keep = max(1, int(keep))
        self.session: str | None = None
        self.turn = 0
        self._actions: list[str] = []  # this session's logged actions, in turn order

    @classmethod
    def from_env(cls, mind: Path, env: Mapping[str, str] | None = None) -> "TransitionLog | None":
        env = os.environ if env is None else env
        if str(env.get("NOEMA_TRANSITION_LOG", "0")).strip() != "1":
            return None
        try:
            max_mb = float(env.get("NOEMA_TRANSITION_LOG_MAX_MB", DEFAULT_MAX_MB))
            keep = int(env.get("NOEMA_TRANSITION_LOG_KEEP", DEFAULT_KEEP))
        except (TypeError, ValueError):
            max_mb, keep = DEFAULT_MAX_MB, DEFAULT_KEEP
        return cls(mind, max_bytes=int(max_mb * 1024 * 1024), keep=keep)

    def new_session(self) -> str:
        """Start a new run of consecutive turns. Rows are only ever paired within one session."""
        self.session = os.urandom(6).hex()
        self.turn = 0
        self._actions = []
        return self.session

    def append(self, *, canonical: Mapping[str, Any], proposal: Any, source: str) -> None:
        if self.session is None:
            self.new_session()
        dropped = [0]
        row = {
            "v": SCHEMA_VERSION,
            "label": "TELEMETRY",
            "ts": int(time.time()),
            "session": self.session,
            "turn": self.turn,
            "seq": canonical.get("sequence"),
            "cycle": canonical.get("cycle"),
            "source": source,
            "obs": _scrub(canonical, dropped),
            "action": {
                "action": getattr(proposal, "action", None),
                "target_id": getattr(proposal, "target_id", None),
                "arguments": _scrub(getattr(proposal, "arguments", None) or {}, dropped),
            },
        }
        if dropped[0]:
            row["redacted_keys"] = dropped[0]
        self._write([row])
        self._actions.append(str(getattr(proposal, "action", "") or "").upper())
        self.turn += 1

    def record_outcomes(self, report: Any) -> int:
        """Label this session's logged turns from the client's turn results (C1, #196).

        `report` is what `client.play()` returned. Every decided turn yields one result that carries a
        proposal, in order; entries without one (the ENTER_WORLD result, a tripped breaker) are not
        decided turns. Labelling stops at the first result whose action differs from the logged one,
        so an outcome is never guessed. Returns the number of turns labelled.
        """
        if self.session is None:
            return 0
        rows = []
        for turn, result in decided_results(self._actions, report):
            row = {"v": SCHEMA_VERSION, "kind": OUTCOME_KIND, "label": "TELEMETRY", "session": self.session,
                   "turn": turn, **outcome_of(result)}
            rows.append(row)
        if rows:
            self._write(rows)
        return len(rows)

    def _write(self, rows: list[dict]) -> None:
        data = "".join(json.dumps(row, sort_keys=True, separators=(",", ":"), default=str) + "\n" for row in rows).encode("utf-8")
        fd = _open_private(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
        try:
            os.write(fd, data)
            size = os.fstat(fd).st_size
        finally:
            os.close(fd)
        if size >= self.max_bytes:
            self._rotate()

    def _segments(self) -> list[tuple[int, Path]]:
        found = []
        for path in self.mind.iterdir():
            match = _SEGMENT_RE.match(path.name)
            if match:
                found.append((int(match.group(1)), path))
        return sorted(found)

    def _rotate(self) -> None:
        segments = self._segments()
        index = (segments[-1][0] + 1) if segments else 1
        target = self.mind / f"transitions-{index:06d}.jsonl.gz"
        partial = target.with_name(target.name + ".part")
        fd = _open_private(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
        with os.fdopen(fd, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as packed, self.path.open("rb") as live:
            shutil.copyfileobj(live, packed, 1 << 16)
        os.replace(partial, target)
        self.path.unlink()
        for _index, old in (segments + [(index, target)])[: -self.keep]:
            old.unlink(missing_ok=True)


def decided_results(actions: list[str], report: Any) -> Iterator[tuple[int, Any]]:
    """Pair a session's decided turns, in order, with the client's results for them.

    `actions` are the upper-cased actions `decide()` returned, in turn order; `report` is what
    `client.play()` returned. Every decided turn yields one result that carries a proposal; entries
    without one (the ENTER_WORLD result, a tripped breaker) are not decided turns. Pairing stops at the
    first result whose action differs from the decided one, so a result is never attributed by guess.
    """
    results = [t for t in (report or []) if getattr(t, "proposal", None) is not None]
    for turn, (decided, result) in enumerate(zip(actions, results)):
        if str(getattr(result.proposal, "action", "") or "").upper() != decided:
            return
        yield turn, result


def _rows(mind: Path, newest_segments: int | None = None) -> Iterator[dict]:
    mind = Path(mind)
    segments = sorted(p for p in mind.iterdir() if _SEGMENT_RE.match(p.name))
    if newest_segments is not None:
        segments = segments[-newest_segments:] if newest_segments > 0 else []
    for segment in segments:
        with gzip.open(segment, "rt", encoding="utf-8") as fh:
            yield from _parse(fh)
    live = mind / LIVE_NAME
    if live.exists():
        with live.open("r", encoding="utf-8") as fh:
            yield from _parse(fh)


def _parse(lines) -> Iterator[dict]:
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:  # a torn final line after a crash
            continue
        if isinstance(row, dict) and row.get("v") == SCHEMA_VERSION:
            yield row


def iter_transitions(mind: Path) -> Iterator[tuple[dict, dict, dict]]:
    """Yield (observation, action, next_observation) for consecutive turns of the same session.

    The last turn of a session has no recorded outcome and is not yielded. A gap (pruned segment,
    crash, new session) is never bridged.
    """
    prev = None
    for row in _rows(mind):
        if row.get("kind") == OUTCOME_KIND:
            continue
        if prev is not None and row.get("session") == prev.get("session") and row.get("turn") == prev.get("turn", -2) + 1:
            yield prev["obs"], prev["action"], row["obs"]
        prev = row


def iter_outcomes(mind: Path) -> Iterator[tuple[dict, dict, dict | None]]:
    """Yield (observation, action, outcome) for every logged turn, including a session's last.

    `outcome` is `{"ok": True}`, or `{"ok": False, "code": ..., "failure": ...}` with the client's own
    rejection code, or None when no result was recorded for that turn (transport drop, crash, a
    session logged before C1, or a pruned segment). None means unknown, never accepted.
    """
    outcomes = {}
    for row in _rows(mind):
        if row.get("kind") == OUTCOME_KIND:
            outcomes[(row.get("session"), row.get("turn"))] = {k: row[k] for k in ("ok", "code", "failure") if k in row}
    for row in _rows(mind):
        if row.get("kind") != OUTCOME_KIND:
            yield row["obs"], row["action"], outcomes.get((row.get("session"), row.get("turn")))


def iter_labelled(mind: Path, newest_segments: int | None = None) -> Iterator[tuple[dict, dict, dict | None, dict | None]]:
    """Yield (observation, action, next_observation, outcome) for every logged turn (C2, #197).

    `next_observation` is None for a session's last turn or across a gap; `outcome` is None when no
    result was recorded. Either can be missing without the other. `newest_segments` limits the read
    to the live file and that many newest rotated segments.
    """
    outcomes = {}
    for row in _rows(mind, newest_segments):
        if row.get("kind") == OUTCOME_KIND:
            outcomes[(row.get("session"), row.get("turn"))] = {k: row[k] for k in ("ok", "code", "failure") if k in row}
    prev = None
    for row in _rows(mind, newest_segments):
        if row.get("kind") == OUTCOME_KIND:
            continue
        if prev is not None:
            follows = row.get("session") == prev.get("session") and row.get("turn") == prev.get("turn", -2) + 1
            yield prev["obs"], prev["action"], row["obs"] if follows else None, outcomes.get((prev.get("session"), prev.get("turn")))
        prev = row
    if prev is not None:
        yield prev["obs"], prev["action"], None, outcomes.get((prev.get("session"), prev.get("turn")))
