#!/usr/bin/env python3
"""Procedures and document lifecycles as state machines, for the Noema repos.

Two sources of truth live beside the agent workflow machine:

  .agents/procedures.json  repeatable procedures (for example the SKILL.* workflows
                           in SKILLS.md) and the issue-triage machine. The Markdown
                           blocks are generated from it.
  .agents/lifecycles.json  document lifecycles (RFCs, ADRs, intents): states, the
                           order they move in, where each document records its
                           state, and the index that must agree with it.

    python3 .agents/docs.py check [--since REF]   CI: blocks in sync, procedures valid,
                                                  every lifecycle document in a legal
                                                  state; with --since, every status
                                                  change since REF moves forward
    python3 .agents/docs.py render [--write]      print or rewrite generated blocks
    python3 .agents/docs.py report                documents per lifecycle state
    python3 .agents/docs.py run SKILL.RFC         start a procedure or runbook (one at a time)
    python3 .agents/docs.py where                 current step, its gate, and the never list
    python3 .agents/docs.py step --evidence "…"   finish the current step
    python3 .agents/docs.py step --user-said "…"  finish a step that needs the user's own words
    python3 .agents/docs.py escalate --evidence "…"
    python3 .agents/docs.py resolve --user-said "…"  clear an escalated procedure once the user has resolved it
    python3 .agents/docs.py triage-audit          open issues not in exactly one triage state (gh)

Runbooks ("runbooks" in procedures.json) are machines that sit beside the
runbook's own text, which stays hand-written: each step names an anchor that
must still appear in the runbook, and a gate (attest, user_yes, run). Steps
marked irreversible, and every step of a human_only runbook, need the user's
own words. The runbook's Never lines are checked to still be in its text.

Known pre-existing lifecycle defects are listed in .agents/docs-baseline.json
with a tracking issue; check fails on new ones and on baseline entries that
have been fixed (remove them). Standard library only; Python 3.10+.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROCEDURES = HERE / "procedures.json"
LIFECYCLES = HERE / "lifecycles.json"
BASELINE = HERE / "docs-baseline.json"
HOW = "generated: edit .agents/procedures.json, then run `python3 .agents/docs.py render --write`"
SKILL_FIELDS = (
    ("use_when", "Use when"), ("inputs", "Inputs"), ("authority", "Authority to read"), ("procedure", "Procedure"),
    ("outputs", "Outputs"), ("validation", "Validation"), ("escalate_when", "Stop / escalate when"),
)


class DocsError(Exception):
    pass


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def start_marker(name: str) -> str:
    return f"<!-- agent-machine:{name}:start · {HOW} -->"


def end_marker(name: str) -> str:
    return f"<!-- agent-machine:{name}:end -->"


# procedures ----------------------------------------------------------------


def steps_of(proc: dict[str, Any]) -> list[str]:
    if "steps" in proc and isinstance(proc["steps"], list) and proc["steps"] and isinstance(proc["steps"][0], dict):
        return [st["do"] for st in proc["steps"]]  # runbook
    p = proc["procedure"]
    return list(p["steps"]) if p["form"] in ("steps", "chain") else [p["text"]]


def find_procedure(procs: dict[str, Any], name: str) -> dict[str, Any] | None:
    return procs.get("skills", {}).get(name) or procs.get("runbooks", {}).get(name)


def step_gate(proc: dict[str, Any], i: int) -> dict[str, Any]:
    """Gate for step i. Runbook steps carry their own; human_only and irreversible steps always need the user."""
    if "runbook" not in proc:
        return {"kind": "attest"}
    st = proc["steps"][i]
    gate = dict(st.get("gate") or {"kind": "attest"})
    if (proc.get("human_only") or st.get("irreversible")) and gate.get("kind") != "user_yes":
        gate = {"kind": "user_yes", "prompt": st.get("prompt", "the user's own words for this step")}
    return gate


def render_skills(skills: dict[str, Any]) -> str:
    out: list[str] = []
    for name, s in skills.items():
        out.append(f"## {name}")
        for key, label in SKILL_FIELDS:
            if key != "procedure":
                out.append(f"**{label}** {s[key]}")
                continue
            p = s["procedure"]
            if p["form"] == "steps":
                out.append(f"**{label}**")
                out += [f"{i}. {step}" for i, step in enumerate(p["steps"], 1)]
            elif p["form"] == "chain":
                out.append(f"**{label}** `{' → '.join(p['steps'])}`.")
            else:
                out.append(f"**{label}** {p['text']}")
        out.append("")
    return "\n".join(out)


def render_triage(t: dict[str, Any]) -> str:
    out = [
        "| Label in mattpocock/skills | Label in our tracker | Meaning |",
        "| -------------------------- | -------------------- | ------- |",
    ]
    out += [f"| `{s['role']}` | `{label}` | {s['meaning']} |" for label, s in t["states"].items()]
    out += [
        "",
        "Each triaged issue carries exactly one state label; an unlabeled issue is untriaged and goes to "
        "`needs-triage` first. The maintainer can override any move. Otherwise:",
        "",
    ]
    for label, s in t["states"].items():
        if s.get("next"):
            out.append(f"- `{label}` → " + " · ".join(f"`{n['to']}` when {n['when']}" for n in s["next"]))
        elif s.get("terminal"):
            out.append(f"- `{label}`: {s['terminal']}")
    out += [
        "",
        "Label strings live in `.agents/procedures.json` (`triage`); edit them there. "
        "`python3 .agents/docs.py triage-audit` lists untriaged issues and issues with conflicting state labels.",
        "",
    ]
    return "\n".join(out)


RENDERERS = {"skills": lambda d: render_skills(d["skills"]), "triage": lambda d: render_triage(d["triage"])}


def blocks(procs: dict[str, Any]) -> list[tuple[Path, str, str]]:
    return [(ROOT / b["file"], b["name"], RENDERERS[b["render"]](procs)) for b in procs.get("blocks", [])]


def current_block(text: str, name: str) -> str | None:
    key, end = f"<!-- agent-machine:{name}:start", end_marker(name)
    if key not in text or end not in text:
        return None
    body = text[text.index(key):]
    body = body[body.index("-->") + 3:]
    return body[: body.index(end)].strip("\n") + "\n"


def splice(text: str, name: str, block: str) -> str:
    key, end = f"<!-- agent-machine:{name}:start", end_marker(name)
    head, rest = text[: text.index(key)], text[text.index(key):]
    tail = rest[rest.index(end) + len(end):]
    return f"{head}{start_marker(name)}\n{block.rstrip(chr(10))}\n{end}{tail}"


def validate_procedures(procs: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    skills = procs.get("skills", {})
    for name, s in skills.items():
        for key, label in SKILL_FIELDS:
            if not s.get(key):
                errs.append(f"{name}: missing {label}")
        p = s.get("procedure", {})
        if p.get("form") not in ("steps", "chain", "prose"):
            errs.append(f"{name}: procedure form must be steps, chain or prose")
        elif not steps_of(s):
            errs.append(f"{name}: procedure has no steps")
        for ref in re.findall(r"SKILL\.[A-Z_]+", json.dumps(s)):
            if ref not in skills:
                errs.append(f"{name}: refers to unknown procedure {ref}")
    for v in procs.get("vendored", []):
        lock = json.loads((ROOT / v["lock"]).read_text(encoding="utf-8")).get("skills", {})
        dirs = {p.parent.name for p in (ROOT / v["dir"]).glob("*/SKILL.md")}
        for name in sorted(set(lock) - dirs):
            errs.append(f"{v['dir']}: {name} is in {v['lock']} but not installed")
        for name in sorted(dirs - set(lock)):
            errs.append(f"{v['dir']}: {name} is installed but not pinned in {v['lock']}")
    for mirror in procs.get("mirrors", []):
        errs += _mirror_errors(procs, mirror)
    for name, rb in procs.get("runbooks", {}).items():
        errs += _runbook_errors(name, rb)
    t = procs.get("triage")
    if t:
        labels = set(t["states"])
        for label, s in t["states"].items():
            for n in s.get("next", []):
                if n["to"] not in labels:
                    errs.append(f"triage {label}: next state {n['to']} is not a triage label")
            if not s.get("next") and not s.get("terminal"):
                errs.append(f"triage {label}: needs next states or a terminal note")
    for path, name, block in blocks(procs):
        if not path.is_file():
            errs.append(f"{path.relative_to(ROOT)}: missing")
            continue
        cur = current_block(path.read_text(encoding="utf-8"), name)
        if cur is None:
            errs.append(f"{path.relative_to(ROOT)}: no agent-machine:{name} block")
        elif cur != block.strip("\n") + "\n":
            errs.append(f"{path.relative_to(ROOT)}: {name} block is out of date: run `python3 .agents/docs.py render --write`")
    return errs


def section(text: str, heading: str | None) -> str | None:
    if heading is None:
        return text
    m = re.search(rf"^{re.escape(heading)}\s*$", text, re.M)
    if not m:
        return None
    rest = text[m.end():]
    nxt = re.search(r"^## ", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def _mirror_errors(procs: dict[str, Any], mirror: dict[str, Any]) -> list[str]:
    """A hand-written doc (for example a skill shipped to players) must stay aligned with machine data."""
    path = ROOT / mirror["file"]
    where_ = f"{mirror['file']}{' ' + mirror['section'] if mirror.get('section') else ''}"
    body = section(path.read_text(encoding="utf-8"), mirror.get("section")) if path.is_file() else None
    if body is None:
        return [f"{where_}: missing (mirror of .agents/procedures.json)"]
    src = procs
    for part in (mirror.get("steps") or mirror.get("mentions")).split("."):
        src = src[part]
    errs = []
    if mirror.get("steps"):
        got = [re.sub(r"^\d+\.\s+", "", ln).strip() for ln in body.splitlines() if re.match(r"^\d+\.\s", ln)]
        if got != list(src):
            errs.append(f"{where_}: numbered steps {got} != {mirror['steps']} {list(src)}")
    else:
        for token in src:
            if token.lower() not in body.lower():
                errs.append(f"{where_}: does not mention {token!r} ({mirror['mentions']})")
    return errs


def _runbook_errors(name: str, rb: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    path = ROOT / rb["runbook"]
    if not path.is_file():
        return [f"{name}: {rb['runbook']} missing"]
    text = path.read_text(encoding="utf-8")
    for key in ("use_when", "escalate_when", "steps"):
        if not rb.get(key):
            errs.append(f"{name}: missing {key}")
    pos = 0
    for i, st in enumerate(rb.get("steps", []), 1):
        anchor = st.get("anchor")
        if anchor:
            at = text.find(anchor, pos)
            if at < 0:
                where_ = "out of order" if anchor in text else "missing"
                errs.append(f"{name} step {i} ({st.get('id')}): anchor {anchor!r} {where_} in {rb['runbook']}")
            else:
                pos = at
        g = st.get("gate", {"kind": "attest"})
        if g.get("kind") not in ("attest", "user_yes", "run"):
            errs.append(f"{name} step {i}: gate kind {g.get('kind')!r}")
        if g.get("kind") == "run" and not g.get("commands"):
            errs.append(f"{name} step {i}: run gate needs commands")
        if st.get("irreversible") and g.get("kind") != "user_yes":
            errs.append(f"{name} step {i} ({st.get('id')}): irreversible steps need a user_yes gate")
    for line in rb.get("never", []):
        if line not in text:
            errs.append(f"{name}: never line {line!r} no longer in {rb['runbook']}")
    lst = rb.get("numbered")
    if lst:
        body = section(text, lst["section"]) or ""
        got = [re.sub(r"^\d+\.\s+", "", ln).strip() for ln in body.splitlines() if re.match(r"^\d+\.\s", ln)]
        want = [st["do"] for st in rb["steps"] if st.get("numbered")]
        if got != want:
            errs.append(f"{name}: numbered steps in {rb['runbook']} {lst['section']} differ from the machine: {got} != {want}")
    return errs


# procedure runner ----------------------------------------------------------


def _git_dir() -> Path:
    try:
        out = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        return (ROOT / out).resolve() / "agent-machine"
    except (OSError, subprocess.CalledProcessError):
        return HERE / ".state"


def _run_path() -> Path:
    return _git_dir() / "procedure.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _save_run(run: dict[str, Any] | None) -> None:
    path = _run_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if run is None:
        path.unlink(missing_ok=True)
    else:
        path.write_text(json.dumps(run, indent=1) + "\n", encoding="utf-8")


def _load_run() -> dict[str, Any] | None:
    path = _run_path()
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def where(procs: dict[str, Any]) -> str:
    names = list(procs.get("skills", {})) + list(procs.get("runbooks", {}))
    if not names:
        return "This repo defines no runnable procedures in .agents/procedures.json."
    run = _load_run()
    if not run:
        return f"No procedure running. Start one: `python3 .agents/docs.py run NAME` ({', '.join(names)})."
    s = find_procedure(procs, run["procedure"])
    assert s is not None
    steps = steps_of(s)
    i = run["step"]
    lines = [f"{run['procedure']}: {s['use_when']}"]
    if "runbook" in s:
        lines[0] += f"  [{s['runbook']}{' · human only' if s.get('human_only') else ''}]"
    if run.get("escalated"):
        lines.append(f"ESCALATED: {run['escalated']} (stop rule: {s['escalate_when']})")
    elif i < len(steps):
        g = step_gate(s, i)
        prompt = g.get("prompt", "the user's own words")
        need = {"attest": '--evidence "…"', "user_yes": f'--user-said "…" ({prompt})', "run": "runs " + ", ".join(g.get("commands", []))}[g["kind"]]
        sid = f" {s['steps'][i].get('id')}" if "runbook" in s else ""
        irr = " IRREVERSIBLE." if "runbook" in s and s["steps"][i].get("irreversible") else ""
        lines += [f"Step {i + 1}/{len(steps)}{sid}: {steps[i]}{irr}", f"Finish with: step {need}", f"Stop / escalate when: {s['escalate_when']}"]
        lines += [f"Never: {n}" for n in s.get("never", [])]
    elif "runbook" in s:
        lines.append("All steps done. `python3 .agents/docs.py step --evidence \"…\"` records where the receipt is.")
    else:
        lines += [f"VALIDATE: {s['validation']}", f"Outputs: {s['outputs']}", "Then `python3 .agents/docs.py step --evidence \"…\"` to finish."]
    return "\n".join(lines)


def run_cmd(procs: dict[str, Any], argv: list[str]) -> str:
    cmd = argv[0]

    def opt(flag: str) -> str:
        return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else ""

    evidence, user_said = opt("--evidence"), opt("--user-said")
    run = _load_run()
    if cmd == "run":
        name = argv[1] if len(argv) > 1 else ""
        if find_procedure(procs, name) is None:
            known = list(procs.get("skills", {})) + list(procs.get("runbooks", {}))
            raise DocsError(f"unknown procedure {name!r}; known: {', '.join(known)}")
        if run and run.get("escalated"):
            raise DocsError(f"{run['procedure']} is escalated; clear it with `resolve --user-said \"…\"`, then run again")
        if run and not run.get("done"):
            raise DocsError(f"{run['procedure']} is still running; finish it (`step`) or `escalate` first")
        _save_run({"procedure": name, "step": 0, "started": _now(), "log": []})
        return where(procs)
    if not run:
        raise DocsError("no procedure running")
    if cmd == "resolve":
        if not run.get("escalated"):
            raise DocsError("nothing to resolve: the procedure is not escalated")
        if not user_said.strip():
            raise DocsError("resolve needs the user's own words: --user-said \"…\"")
        _save_run(None)
        return f"{run['procedure']} resolved ({user_said!r}); start it again with `run {run['procedure']}` if needed."
    if cmd == "escalate":
        if not evidence:
            raise DocsError("escalate needs --evidence")
        run["escalated"] = evidence
        run["log"].append({"ts": _now(), "escalated": evidence})
        _save_run(run)
        return where(procs)
    if cmd == "step":
        if run.get("escalated"):
            raise DocsError("procedure is escalated; once the user has resolved it: `resolve --user-said \"…\"`")
        proc = find_procedure(procs, run["procedure"])
        assert proc is not None
        steps = steps_of(proc)
        ran: list[dict[str, Any]] = []
        if run["step"] < len(steps):
            g = step_gate(proc, run["step"])
            if g["kind"] == "user_yes":
                if not user_said.strip():
                    raise DocsError(f"this step needs the user's own words: --user-said \"…\" ({g.get('prompt', '')})")
                if g.get("must_match") and not re.search(g["must_match"], user_said):
                    raise DocsError(f"the user's words must match {g['must_match']!r} ({g.get('prompt', '')})")
            elif g["kind"] == "run":
                for c in g["commands"]:
                    code = subprocess.run(shlex.split(c), cwd=ROOT).returncode
                    ran.append({"cmd": c, "exit": code})
                    if code != 0:
                        raise DocsError(f"step blocked: `{c}` exited {code}")
            elif not evidence:
                raise DocsError("step needs --evidence")
        elif not evidence:
            raise DocsError("step needs --evidence")
        run["log"].append({"ts": _now(), "step": run["step"] + 1, "evidence": evidence, "user_said": user_said, "ran": ran})
        if run["step"] >= len(steps):
            _save_run(None)
            return f"{run['procedure']} done ({len(run['log'])} entries)."
        run["step"] += 1
        _save_run(run)
        return where(procs)
    raise DocsError(f"unknown command {cmd}")


# lifecycles ----------------------------------------------------------------


def status_text(text: str, patterns: list[str]) -> str | None:
    for pat in patterns:
        m = re.search(pat, text, re.M | re.I)
        if m:
            return m.group(1).strip()
    return None


def normalize(raw: str | None, kind: dict[str, Any]) -> str | None:
    """The state whose keyword appears first in the status text ("Draft; not accepted" is Draft)."""
    if not raw:
        return None
    low = re.sub(r"\[[^\]]*\]\([^)]*\)", " ", raw).lower()
    best: tuple[int, str] | None = None
    for st in kind["states"]:
        for alias in kind["aliases"][st]:
            m = re.search(rf"\b{re.escape(alias)}\b", low)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), st)
    return best[1] if best else None


def entries(kind: dict[str, Any], text: str | None = None) -> dict[str, str]:
    """For kinds that live as headed entries in one file: id -> raw status."""
    e = kind["entries"]
    text = (ROOT / e["file"]).read_text(encoding="utf-8") if text is None else text
    return {m.group("id"): m.group("status").strip() for m in re.finditer(e["heading"], text, re.M)}


_ITEM = re.compile(r"^\s*[-*] \[([ xX])\] (.+?)\s*$", re.M)


def checklist_items(text: str) -> dict[str, bool]:
    """Checklist item text -> done."""
    return {m.group(2): m.group(1).lower() == "x" for m in _ITEM.finditer(text)}


def documents(kind: dict[str, Any]) -> dict[str, Path]:
    globs = kind["files"] if isinstance(kind["files"], list) else [kind["files"]]
    files = sorted({p for g in globs for p in ROOT.glob(g)})
    return {
        (p.name if p.name != "spec.md" or p.parent.name == "specify" else f"{p.parent.name}/{p.name}"): p
        for p in files
        if not any(fnmatch.fnmatch(str(p.relative_to(ROOT)), x) for x in kind.get("exclude", []))
    }


def index_rows(kind: dict[str, Any], text: str | None = None) -> dict[str, str]:
    idx = kind.get("index")
    if not idx:
        return {}
    if text is None:
        text = (ROOT / idx["file"]).read_text(encoding="utf-8")
    return {Path(m.group("file")).name: m.group("status") for m in re.finditer(idx["row"], text, re.M)}


def forward(kind: dict[str, Any], old: str, new: str) -> bool:
    return old == new or new in kind["next"].get(old, [])


def lifecycle_violations(lc: dict[str, Any], since: str | None = None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for kid, kind in lc.get("kinds", {}).items():
        if "entries" in kind:
            out += _entry_violations(kid, kind, since)
            continue
        if "checklist" in kind:
            out += _checklist_violations(kid, kind, since)
            continue
        docs = documents(kind)
        index = index_rows(kind)
        old_index: dict[str, str] = {}
        if since and kind.get("index"):
            prev_idx = subprocess.run(
                ["git", "show", f"{since}:{kind['index']['file']}"],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            if prev_idx.returncode == 0:
                old_index = index_rows(kind, prev_idx.stdout)
        for fname, path in docs.items():
            raw = status_text(path.read_text(encoding="utf-8"), kind["status"])
            ref = f"{kid}:{fname}"
            if raw is None and fname in index:  # the index alone may carry the status (e.g. RFC-0001)
                raw = index[fname]
            if raw is None and kind.get("default"):  # format says a bare record is in this state
                raw = kind["default"]
            state = normalize(raw, kind)
            if raw is None:
                out.append({"key": f"{ref}:no_status", "detail": "no status in the file or its index"})
            elif state is None:
                out.append({"key": f"{ref}:unknown_status", "detail": f"status {raw[:80]!r} is not a {kind['title']} state ({', '.join(kind['states'])})"})
            if kind.get("index"):
                if fname not in index:
                    out.append({"key": f"{ref}:not_in_index", "detail": f"missing from {kind['index']['file']}"})
                else:
                    istate = normalize(index[fname], kind)
                    if istate is None:
                        out.append({"key": f"{ref}:unknown_index_status", "detail": f"index status {index[fname][:80]!r} is not a {kind['title']} state ({', '.join(kind['states'])})"})
                    elif state and istate != state:
                        out.append({"key": f"{ref}:index_mismatch", "detail": f"file says {state}, index says {istate}"})
            need = kind.get("links", {}).get(state or "")
            if need and raw:
                targets = [need["file_prefix"].format(int(t) if t.isdigit() else t) for t in re.findall(need["pattern"], raw)]
                if not targets or not all(any(n.startswith(t) for n in docs) for t in targets):
                    out.append({"key": f"{ref}:missing_successor", "detail": f"{state} must name an existing successor ({need['pattern']})"})
            for req in kind.get("requires", []):
                if state not in req["when"]:
                    continue
                m = re.search(req["field"], path.read_text(encoding="utf-8"), re.M)
                if not m:
                    continue
                other = lc["kinds"][req["kind"]]
                target = Path(m.group(1)).name
                tdocs = documents(other)
                if target not in tdocs:
                    out.append({"key": f"{ref}:requires_missing:{target}", "detail": f"names {req['kind']} {target}, which does not exist"})
                    continue
                tstate = normalize(status_text(tdocs[target].read_text(encoding="utf-8"), other["status"]), other)
                order = other["states"]
                if tstate is None or order.index(tstate) < order.index(req["min_state"]):
                    out.append({"key": f"{ref}:requires:{target}", "detail": f"is {state} but its {req['kind']} {target} is {tstate} (needs {req['min_state']})"})
            if since and state:
                old = subprocess.run(["git", "show", f"{since}:{path.relative_to(ROOT)}"], cwd=ROOT, capture_output=True, text=True)
                if old.returncode == 0:
                    old_raw = status_text(old.stdout, kind["status"])
                    if old_raw is None and fname in old_index:
                        old_raw = old_index[fname]
                    if old_raw is None and kind.get("default"):
                        old_raw = kind["default"]
                    old_state = normalize(old_raw, kind)
                    if old_state and not forward(kind, old_state, state):
                        out.append({"key": f"{ref}:backward:{old_state}->{state}", "detail": f"{old_state} → {state} is not a forward move ({kind['declared']})"})
        for fname in index:
            if fname not in docs:
                out.append({"key": f"{kid}:{fname}:index_without_file", "detail": f"{kind['index']['file']} lists a file that does not exist"})
    return out


def _checklist_violations(kid: str, kind: dict[str, Any], since: str | None) -> list[dict[str, str]]:
    """Items are open -> done. Only an exact-text item going from done back to open is a backward move."""
    rel = kind["checklist"]
    path = ROOT / rel
    if not path.is_file():
        return [{"key": f"{kid}:missing", "detail": f"{rel} missing"}]
    if not since:
        return []
    prev = subprocess.run(["git", "show", f"{since}:{rel}"], cwd=ROOT, capture_output=True, text=True)
    if prev.returncode != 0:
        return []
    before, now = checklist_items(prev.stdout), checklist_items(path.read_text(encoding="utf-8"))
    return [
        {"key": f"{kid}:unchecked:{hashlib.sha256(item.encode()).hexdigest()[:12]}", "detail": f"{rel}: done item reopened: {item[:90]!r}"}
        for item, done in now.items() if not done and before.get(item) is True
    ]


def _entry_violations(kid: str, kind: dict[str, Any], since: str | None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    rel = kind["entries"]["file"]
    now = entries(kind)
    old: dict[str, str] = {}
    if since:
        prev = subprocess.run(["git", "show", f"{since}:{rel}"], cwd=ROOT, capture_output=True, text=True)
        old = entries(kind, prev.stdout) if prev.returncode == 0 else {}
    for eid, raw in now.items():
        state = normalize(raw, kind)
        if state is None:
            out.append({"key": f"{kid}:{eid}:unknown_status", "detail": f"{rel}: status {raw!r} is not a {kind['title']} state ({', '.join(kind['states'])})"})
        elif eid in old:
            before = normalize(old[eid], kind)
            if before and not forward(kind, before, state):
                out.append({"key": f"{kid}:{eid}:backward:{before}->{state}", "detail": f"{before} → {state} is not a forward move ({kind['declared']})"})
    for eid in old:
        if eid not in now:
            out.append({"key": f"{kid}:{eid}:removed", "detail": f"{rel}: entry removed; record a new status instead"})
    return out


def report(lc: dict[str, Any]) -> str:
    lines = []
    for kid, kind in lc.get("kinds", {}).items():
        if "checklist" in kind:
            items = checklist_items((ROOT / kind["checklist"]).read_text(encoding="utf-8"))
            done = sum(items.values())
            lines.append(f"{kind['title']}: done {done}, open {len(items) - done}   [{kind['declared']}]")
            continue
        if "entries" in kind:
            counts_e: dict[str, int] = {}
            for raw in entries(kind).values():
                st = normalize(raw, kind) or "(unrecognized)"
                counts_e[st] = counts_e.get(st, 0) + 1
            lines.append(f"{kind['title']}: " + ", ".join(f"{s} {n}" for s, n in counts_e.items()) + f"   [{kind['declared']}]")
            continue
        counts: dict[str, int] = {}
        index = index_rows(kind)
        for fname, path in documents(kind).items():
            raw = status_text(path.read_text(encoding="utf-8"), kind["status"]) or index.get(fname) or kind.get("default")
            st = normalize(raw, kind) or "(unrecognized)"
            counts[st] = counts.get(st, 0) + 1
        order = kind["states"] + ["(unrecognized)"]
        lines.append(f"{kind['title']}: " + ", ".join(f"{s} {counts[s]}" for s in order if s in counts) + f"   [{kind['declared']}]")
    return "\n".join(lines)


# CLI -----------------------------------------------------------------------


def check(since: str | None = None) -> list[str]:
    procs, lc, base = _read(PROCEDURES), _read(LIFECYCLES), _read(BASELINE)
    errs = validate_procedures(procs) if procs else []
    known = {b["key"] for b in base.get("known", [])}
    found = lifecycle_violations(lc, since) if lc else []
    keys = {v["key"] for v in found}
    for v in found:
        if v["key"] not in known:
            errs.append(f"{v['key']}: {v['detail']}")
    for k in sorted(known - keys):
        errs.append(f"{k}: fixed; remove it from .agents/docs-baseline.json")
    return errs


def triage_audit(procs: dict[str, Any]) -> str:
    labels = set(procs["triage"]["states"])
    repo = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    if not repo:
        url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        repo = re.sub(r"(\.git)?$", "", url.split("github.com/")[-1].split("github.com:")[-1])
    data = subprocess.run(
        ["gh", "api", f"repos/{repo}/issues?state=open&per_page=100", "--paginate", "--slurp"], capture_output=True, text=True
    )
    if data.returncode != 0:
        raise DocsError(f"gh api failed: {data.stderr.strip()[:200]}")
    issues = [i for page in json.loads(data.stdout) for i in page if "pull_request" not in i]
    untriaged, conflicts = [], []
    for i in issues:
        mine = sorted(lbl["name"] for lbl in i["labels"] if lbl["name"] in labels)
        line = f"#{i['number']} {', '.join(mine) or '(no state label)'}: {i['title'][:70]}"
        if not mine:
            untriaged.append(line)
        elif len(mine) > 1:
            conflicts.append(line)
    out = f"{repo}: {len(issues)} open issues, {len(conflicts)} with conflicting state labels, {len(untriaged)} untriaged"
    out += "".join(f"\n  CONFLICT {c}" for c in conflicts) + "".join(f"\n  untriaged {u}" for u in untriaged)
    return out


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0 if argv else 2
    procs = _read(PROCEDURES)
    try:
        if argv[0] == "check":
            since = argv[argv.index("--since") + 1] if "--since" in argv else None
            errs = check(since)
            for e in errs:
                print(f"docs-machine: {e}", file=sys.stderr)
            if not errs:
                n = len(_read(BASELINE).get("known", []))
                vend = sum(len(json.loads((ROOT / v["lock"]).read_text()).get("skills", {})) for v in procs.get("vendored", []))
                print(f"docs-machine ok: {len(procs.get('skills', {}))} procedures, {len(procs.get('runbooks', {}))} runbooks, {vend} vendored pinned, lifecycles legal ({n} known defects baselined)")
            return 1 if errs else 0
        if argv[0] == "render":
            for path, name, block in blocks(procs):
                if "--write" in argv:
                    path.write_text(splice(path.read_text(encoding="utf-8"), name, block), encoding="utf-8")
                    print(f"{path.relative_to(ROOT)}: {name} block rewritten")
                else:
                    print(f"=== {path.relative_to(ROOT)} [{name}]\n{block}")
            return 0
        if argv[0] == "report":
            print(report(_read(LIFECYCLES)))
            return 0
        if argv[0] == "where":
            print(where(procs))
            return 0
        if argv[0] in ("run", "step", "escalate", "resolve"):
            print(run_cmd(procs, argv))
            return 0
        if argv[0] == "triage-audit":
            print(triage_audit(procs))
            return 0
    except DocsError as exc:
        print(f"docs-machine: {exc}", file=sys.stderr)
        return 1
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
