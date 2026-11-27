#!/usr/bin/env python3
"""Agent workflow state machine for the Noema repos. The same file ships in all four repos.

.agents/machine.json is the source of truth: a shared "core" (identical in
every repo, guarded by meta.core_digest) plus this repo's "repo" overlay. The
workflow block of AGENTS.md is rendered from it, and agents track their
current state with this tool.

    python3 .agents/machine.py status                 where am I, what may I do, where next
    python3 .agents/machine.py go STATE --evidence "…" take a transition (guards are checked)
    python3 .agents/machine.py go AWAITING_USER --evidence "summary asked"
    python3 .agents/machine.py go DEPLOY_APPROVED --user-said "deploy it"
    python3 .agents/machine.py log                    transition history (this clone)
    python3 .agents/machine.py reset                  back to the initial state
    python3 .agents/machine.py render [--write]       print or rewrite the AGENTS.md block
    python3 .agents/machine.py check                  CI: machine valid, core digest, AGENTS.md in sync
    python3 .agents/machine.py digest                 core digest, after an intentional core change

State lives in the git directory (never committed, per clone or worktree).
Standard library only; Python 3.10+.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MACHINE = HERE / "machine.json"
AGENTS_MD = ROOT / "AGENTS.md"
START = "<!-- agent-machine:start · generated: edit .agents/machine.json, then run `python3 .agents/machine.py render --write` -->"
END = "<!-- agent-machine:end -->"
RESUME = "@resume"
TIERS = ("pre_authorized", "needs_user", "never", "documented", "unstated")
GUARDS = ("none", "attest", "user_yes", "run")
CORE_REPOS = "Noema, Noema-Specs, Noema-Orin and noema-client"


class MachineError(Exception):
    pass


# model ---------------------------------------------------------------------


@dataclass
class Exit:
    to: str
    when: str
    guard: dict[str, Any] = field(default_factory=lambda: {"kind": "none"})


@dataclass
class State:
    id: str
    summary: str
    do: list[str]
    allow: list[str]
    exits: list[Exit]
    terminal: bool = False
    no_global_exits: bool = False


@dataclass
class Machine:
    raw: dict[str, Any]
    initial: str
    states: dict[str, State]
    global_exits: list[Exit]
    actions: dict[str, dict[str, Any]]
    repo: dict[str, Any]

    def exits_from(self, state: str) -> list[Exit]:
        own = self.states[state].exits
        if self.states[state].no_global_exits:
            return own
        targets = {e.to for e in own}
        extra = [g for g in self.global_exits if g.to != state and g.to not in targets]
        return own + extra

    def tier(self, action: str) -> str:
        return self.actions.get(action, {}).get("tier", "unstated")


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def core_digest(raw: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical(raw["core"]).encode()).hexdigest()


def _exits(items: list[dict[str, Any]], verify: list[str] | None = None) -> list[Exit]:
    out = []
    for e in items:
        guard = dict(e.get("guard") or {"kind": "none"})
        if guard.get("commands") == "@verify":
            guard["commands"] = list(verify or [])
        out.append(Exit(e["to"], e.get("when", ""), guard))
    return out


def _state(sid: str, s: dict[str, Any], verify: list[str]) -> State:
    return State(
        sid, s["summary"], list(s.get("do", [])), list(s.get("allow", [])), _exits(s.get("exits", []), verify),
        bool(s.get("terminal")), bool(s.get("no_global_exits")),
    )


def load(path: Path = MACHINE) -> Machine:
    raw = json.loads(path.read_text(encoding="utf-8"))
    core, repo = raw["core"], raw.get("repo", {})
    verify = list(repo.get("verify", []))
    states: dict[str, State] = {sid: _state(sid, s, verify) for sid, s in core["states"].items()}
    for sid, s in repo.get("states", {}).items():
        if sid in states:  # overlay may only extend a core state
            unknown = set(s) - {"do_extra", "allow_extra", "exits_extra"}
            if unknown:
                raise MachineError(f"repo overlay may only extend core state {sid} (do_extra, allow_extra, exits_extra); got {sorted(unknown)}")
            states[sid].do += s.get("do_extra", [])
            states[sid].allow += s.get("allow_extra", [])
            states[sid].exits += _exits(s.get("exits_extra", []), verify)
        else:
            states[sid] = _state(sid, s, verify)
    actions = {k: dict(v) for k, v in core.get("actions", {}).items()}
    for k, v in repo.get("actions", {}).items():
        actions.setdefault(k, {}).update(v)
    return Machine(raw, core["initial"], states, _exits(core.get("global_exits", [])), actions, repo)


# validation ----------------------------------------------------------------


def validate(m: Machine) -> list[str]:
    errs: list[str] = []
    if m.raw.get("format") != "noema-agent-machine/1":
        errs.append("format must be noema-agent-machine/1")
    want = m.raw.get("meta", {}).get("core_digest")
    got = core_digest(m.raw)
    if want != got:
        errs.append(
            f"core changed (meta.core_digest {want} != {got}). The core must stay identical in {CORE_REPOS}: "
            "apply the same edit to every repo, then set core_digest from `python3 .agents/machine.py digest`."
        )
    if m.initial not in m.states:
        errs.append(f"initial state {m.initial} is not defined")
    for aid, a in m.actions.items():
        if a.get("tier") not in TIERS:
            errs.append(f"action {aid}: tier {a.get('tier')!r} not in {TIERS}")
        if not a.get("text"):
            errs.append(f"action {aid}: text is required")
    user_gated = set()
    for s in m.states.values():
        for e in m.exits_from(s.id):
            kind = e.guard.get("kind")
            if kind not in GUARDS:
                errs.append(f"{s.id} -> {e.to}: guard kind {kind!r} not in {GUARDS}")
            if e.to != RESUME and e.to not in m.states:
                errs.append(f"{s.id} -> {e.to}: unknown target state")
            if kind == "run" and not e.guard.get("commands"):
                errs.append(f"{s.id} -> {e.to}: run guard needs commands")
            if kind == "user_yes":
                user_gated.add(e.to)
        for a in s.allow:
            if a not in m.actions:
                errs.append(f"{s.id}: allows unknown action {a}")
            elif m.tier(a) == "never":
                errs.append(f"{s.id}: allows never-tier action {a}")
        if not s.terminal and not m.exits_from(s.id):
            errs.append(f"{s.id}: non-terminal state has no exit")
    # needs_user actions only in states every incoming edge reaches through a user_yes guard
    for s in m.states.values():
        gated = [a for a in s.allow if m.tier(a) == "needs_user"]
        if not gated:
            continue
        incoming = [(src.id, e) for src in m.states.values() for e in m.exits_from(src.id) if e.to == s.id]
        if not incoming or any(e.guard.get("kind") != "user_yes" for _, e in incoming):
            errs.append(f"{s.id}: allows needs_user actions {gated} but is reachable without a user_yes guard")
    # reachability from the initial state
    seen, todo = set(), [m.initial] if m.initial in m.states else []
    while todo:
        sid = todo.pop()
        if sid in seen:
            continue
        seen.add(sid)
        todo += [e.to for e in m.exits_from(sid) if e.to in m.states]
    for sid in m.states:
        if sid not in seen:
            errs.append(f"{sid}: unreachable from {m.initial}")
    return errs


# rendering -----------------------------------------------------------------


def main_path(m: Machine) -> list[str]:
    """Follow each state's first exit from the initial state: the happy path."""
    path, sid = [], m.initial
    while sid in m.states and sid not in path:
        path.append(sid)
        exits = m.states[sid].exits
        sid = exits[0].to if exits else ""
    return path


def _when(e: Exit) -> str:
    return f" when {e.when}" if e.when else ""


def _to(e: Exit) -> str:
    return "back" if e.to == RESUME else e.to


def render(m: Machine) -> str:
    r = m.repo
    path = main_path(m)
    globals_ = [g.to for g in m.global_exits]
    out = [START, "", f"## {r.get('heading', 'Workflow')}", ""]
    out += [
        "Agent work is a state machine (`.agents/machine.json`): `python3 .agents/machine.py status` shows "
        "where you are and what is allowed; `go STATE` moves.",
        "",
        f"**Path:** {' → '.join(path)}.",
    ]
    for i, sid in enumerate(path):
        nxt = path[i + 1] if i + 1 < len(path) else None
        for e in m.states[sid].exits:
            if e.to != nxt and not (i == len(path) - 1 and e.to == m.initial):
                out.append(f"- {sid} → {_to(e)}{_when(e)}.")
    for sid in path:
        s = m.states[sid]
        lines = list(s.do)
        run = [e for e in s.exits if e.guard.get("kind") == "run"]
        if run:
            lines.append(f"`go {run[0].to}` runs " + ", ".join(f"`{c}`" for c in run[0].guard["commands"]) + ".")
        if lines:
            out.append(f"- **{sid}**: {' '.join(lines)}")
    side = []
    for sid in r.get("order") or list(m.states):
        if sid in path or sid in globals_:
            continue
        side.append(sid)
        s = m.states[sid]
        incoming = [f"{src.id}{_when(e)}" for src in m.states.values() for e in src.exits if e.to == sid]
        back = " · ".join(f"{_to(e)}{_when(e)}" for e in s.exits)
        out.append(f"- **{sid}** (from {'; '.join(incoming)}): {' '.join(s.do) or s.summary} Then: {back}.")
    for g in m.global_exits:
        s = m.states[g.to]
        back = " · ".join(f"{_to(e)}{_when(e)}" for e in s.exits if e.to not in side) or "see above"
        out.append(f"- **Any state → {g.to}** {g.when}: {' '.join(s.do) or s.summary} Then: {back}.")
    out += [f"- {note}" for note in r.get("notes", [])]
    out.append("")
    grant = r.get("grant")
    if grant:
        out += [f"## {grant.get('heading', 'Standing grant')}", "", grant["preamble"], ""]
        for tier, title in (("pre_authorized", "Pre-authorized, no confirmation needed"), ("needs_user", "Needs me, once per occurrence"), ("never", "Never")):
            out += [f"### {title}"] + [f"- {a['text']}" for a in m.actions.values() if a.get("tier") == tier] + [""]
    out.append(END)
    return "\n".join(out)


def splice(text: str, block: str) -> str:
    if START.split(" ·")[0] not in text or END not in text:
        raise MachineError("AGENTS.md has no agent-machine markers")
    head = text[: text.index(START.split(" ·")[0])]
    tail = text[text.index(END) + len(END):]
    return head + block + tail


def current_block(text: str) -> str | None:
    key = START.split(" ·")[0]
    if key not in text or END not in text:
        return None
    return text[text.index(key): text.index(END) + len(END)]


# runtime state -------------------------------------------------------------


def state_dir() -> Path:
    try:
        git_dir = subprocess.run(
            ["git", "rev-parse", "--git-dir"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
        base = (ROOT / git_dir).resolve()
    except (OSError, subprocess.CalledProcessError):
        base = HERE / ".state"
    return base / "agent-machine"


def read_state(m: Machine) -> dict[str, Any]:
    path = state_dir() / "state.json"
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("state") in m.states:
            return data
    return {"state": m.initial, "previous": None, "resume": None, "since": None}


def _write_state(data: dict[str, Any], event: dict[str, Any]) -> None:
    d = state_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    with open(d / "log.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def allowed(action: str, m: Machine | None = None) -> tuple[bool, str]:
    """May the agent take `action` now? Returns (ok, reason)."""
    m = m or load()
    st = read_state(m)["state"]
    tier = m.tier(action)
    if action not in m.actions:
        return False, f"unknown action {action!r}"
    if tier == "never":
        return False, f"{action} is never allowed: {m.actions[action]['text']}"
    if action not in m.states[st].allow:
        where = [s.id for s in m.states.values() if action in s.allow]
        return False, f"{action} is not allowed in {st}; allowed in: {', '.join(where) or 'no state'}"
    return True, f"{action} allowed in {st} ({tier})"


def allowed_actions(m: Machine | None = None) -> tuple[str, list[str]]:
    m = m or load()
    st = read_state(m)["state"]
    return st, [a for a in m.states[st].allow if m.tier(a) != "never"]


def go(m: Machine, target: str, *, evidence: str = "", user_said: str = "", no_run: bool = False) -> str:
    cur = read_state(m)
    sid = cur["state"]
    target = target.upper() if target.upper() in m.states else target
    for e in m.exits_from(sid):
        dest = cur.get("resume") if e.to == RESUME else e.to
        if target in (e.to, dest) or (target.lower() == "back" and e.to == RESUME):
            break
    else:
        options = ", ".join((cur.get("resume") or "back") if x.to == RESUME else x.to for x in m.exits_from(sid))
        raise MachineError(f"no transition {sid} -> {target}; from {sid} you can go to: {options}")
    if not dest:
        raise MachineError(f"{sid} -> back: no state to resume")
    # A global exit (STOPPED, ESCALATED, AWAITING_USER) remembers where to come back to.
    resume = cur.get("resume")
    if any(e is g for g in m.global_exits) and not resume:
        resume = sid
    if e.to == RESUME or dest == m.initial:
        resume = None
    g, ran = e.guard, []
    kind = g.get("kind", "none")
    if kind == "attest" and not evidence.strip():
        raise MachineError(f"{sid} -> {dest} needs --evidence: {g.get('prompt', e.when)}")
    if kind == "user_yes":
        if not user_said.strip():
            raise MachineError(f"{sid} -> {dest} needs the user's own words: --user-said \"…\" ({g.get('prompt', e.when)})")
        pattern = g.get("must_match")
        if pattern and not re.search(pattern, user_said):
            raise MachineError(f"{sid} -> {dest}: the user's words must match {pattern!r} ({g.get('prompt', '')})")
    if kind == "run":
        if no_run:
            if not evidence.strip():
                raise MachineError("--no-run needs --evidence saying why the checks were skipped")
        else:
            for cmd in g["commands"]:
                proc = subprocess.run(shlex.split(cmd), cwd=ROOT)
                ran.append({"cmd": cmd, "exit": proc.returncode})
                if proc.returncode != 0:
                    raise MachineError(f"{sid} -> {dest} blocked: `{cmd}` exited {proc.returncode}")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_state(
        {"state": dest, "previous": sid, "resume": resume, "since": now},
        {"ts": now, "from": sid, "to": dest, "guard": kind, "evidence": evidence, "user_said": user_said, "ran": ran, "skipped_checks": no_run},
    )
    return dest


def status(m: Machine) -> str:
    cur = read_state(m)
    s = m.states[cur["state"]]
    lines = [f"State: {s.id}" + (f" (since {cur['since']}, from {cur['previous']})" if cur.get("since") else " (initial)"), f"  {s.summary}"]
    if s.do:
        lines += ["Do:"] + [f"  - {d}" for d in s.do]
    lines += ["Allowed here:"] + [f"  - {a} [{m.tier(a)}]: {m.actions[a]['text']}" for a in s.allow]
    lines.append("Next:")
    for e in m.exits_from(s.id):
        dest = (cur.get("resume") or "?") if e.to == RESUME else e.to
        g = e.guard.get("kind", "none")
        need = {"attest": ' --evidence "…"', "user_yes": ' --user-said "…"', "run": " (runs checks)"}.get(g, "")
        lines.append(f"  go {dest}{need}  — {e.when}")
    return "\n".join(lines)


# CLI -----------------------------------------------------------------------


def _opt(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else ""


def check(m: Machine) -> list[str]:
    errs = validate(m)
    if AGENTS_MD.is_file():
        block = current_block(AGENTS_MD.read_text(encoding="utf-8"))
        if block is None:
            errs.append("AGENTS.md has no agent-machine block")
        elif block != render(m):
            errs.append("AGENTS.md workflow block is out of date: run `python3 .agents/machine.py render --write`")
    return errs


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    cmd, m = argv[0], load()
    try:
        if cmd == "check":
            errs = check(m)
            for e in errs:
                print(f"agent-machine: {e}", file=sys.stderr)
            if not errs:
                print(f"agent-machine ok: {len(m.states)} states, {len(m.actions)} actions, core {core_digest(m.raw)[:19]}")
            return 1 if errs else 0
        if cmd == "digest":
            print(core_digest(m.raw))
            return 0
        if cmd == "render":
            block = render(m)
            if "--write" in argv:
                AGENTS_MD.write_text(splice(AGENTS_MD.read_text(encoding="utf-8"), block), encoding="utf-8")
                print("AGENTS.md block rewritten")
            else:
                print(block)
            return 0
        if cmd == "status":
            print(status(m))
            return 0
        if cmd == "go" and len(argv) > 1:
            dest = go(m, argv[1], evidence=_opt(argv, "--evidence"), user_said=_opt(argv, "--user-said"), no_run="--no-run" in argv)
            print(f"-> {dest}\n")
            print(status(m))
            return 0
        if cmd == "log":
            path = state_dir() / "log.jsonl"
            print(path.read_text(encoding="utf-8").rstrip() if path.is_file() else "(no transitions yet)")
            return 0
        if cmd == "reset":
            _write_state({"state": m.initial, "previous": None, "resume": None, "since": None}, {"ts": datetime.now(timezone.utc).isoformat(), "reset": True})
            print(f"-> {m.initial}")
            return 0
        if cmd == "allowed" and len(argv) > 1:
            ok, why = allowed(argv[1], m)
            print(why)
            return 0 if ok else 1
    except MachineError as exc:
        print(f"agent-machine: {exc}", file=sys.stderr)
        return 1
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
