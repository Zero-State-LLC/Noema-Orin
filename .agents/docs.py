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
    python3 .agents/docs.py run SKILL.RFC         start a procedure (one at a time)
    python3 .agents/docs.py where                 current procedure step
    python3 .agents/docs.py step --evidence "…"   finish the current step
    python3 .agents/docs.py escalate --evidence "…"
    python3 .agents/docs.py triage-audit          open issues not in exactly one triage state (gh)

Known pre-existing lifecycle defects are listed in .agents/docs-baseline.json
with a tracking issue; check fails on new ones and on baseline entries that
have been fixed (remove them). Standard library only; Python 3.10+.
"""

from __future__ import annotations

import fnmatch
import json
import re
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
    p = proc["procedure"]
    return list(p["steps"]) if p["form"] in ("steps", "chain") else [p["text"]]


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
    out += ["", "Each open issue carries exactly one triage label. It moves like this:", ""]
    for label, s in t["states"].items():
        if s.get("next"):
            out.append(f"- `{label}` → " + " · ".join(f"`{n['to']}` when {n['when']}" for n in s["next"]))
        elif s.get("terminal"):
            out.append(f"- `{label}`: {s['terminal']}")
    out += [
        "",
        "Label strings live in `.agents/procedures.json` (`triage`); edit them there. "
        "`python3 .agents/docs.py triage-audit` lists open issues that break the rule.",
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
    if not procs.get("skills"):
        return "This repo defines no runnable procedures in .agents/procedures.json."
    run = _load_run()
    if not run:
        return "No procedure running. Start one: `python3 .agents/docs.py run SKILL.ORIENT`."
    s = procs["skills"][run["procedure"]]
    steps = steps_of(s)
    i = run["step"]
    lines = [f"{run['procedure']}: {s['use_when']}"]
    if run.get("escalated"):
        lines.append(f"ESCALATED: {run['escalated']} (stop rule: {s['escalate_when']})")
    elif i < len(steps):
        lines += [f"Step {i + 1}/{len(steps)}: {steps[i]}", f"Stop / escalate when: {s['escalate_when']}"]
    else:
        lines += [f"VALIDATE: {s['validation']}", f"Outputs: {s['outputs']}", "Then `python3 .agents/docs.py step --evidence \"…\"` to finish."]
    return "\n".join(lines)


def run_cmd(procs: dict[str, Any], argv: list[str]) -> str:
    cmd = argv[0]
    evidence = argv[argv.index("--evidence") + 1] if "--evidence" in argv and argv.index("--evidence") + 1 < len(argv) else ""
    run = _load_run()
    if cmd == "run":
        name = argv[1] if len(argv) > 1 else ""
        if name not in procs.get("skills", {}):
            raise DocsError(f"unknown procedure {name!r}; known: {', '.join(procs.get('skills', {}))}")
        if run and not run.get("done"):
            raise DocsError(f"{run['procedure']} is still running; finish it (`step`) or `escalate` first")
        _save_run({"procedure": name, "step": 0, "started": _now(), "log": []})
        return where(procs)
    if not run:
        raise DocsError("no procedure running")
    if cmd == "escalate":
        if not evidence:
            raise DocsError("escalate needs --evidence")
        run["escalated"] = evidence
        run["log"].append({"ts": _now(), "escalated": evidence})
        _save_run(run)
        return where(procs)
    if cmd == "step":
        if run.get("escalated"):
            raise DocsError("procedure is escalated; resolve it with the user, then `run` again")
        if not evidence:
            raise DocsError("step needs --evidence")
        steps = steps_of(procs["skills"][run["procedure"]])
        run["log"].append({"ts": _now(), "step": run["step"] + 1, "evidence": evidence})
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


def documents(kind: dict[str, Any]) -> dict[str, Path]:
    files = sorted(ROOT.glob(kind["files"]))
    return {p.name: p for p in files if not any(fnmatch.fnmatch(str(p.relative_to(ROOT)), x) for x in kind.get("exclude", []))}


def index_rows(kind: dict[str, Any]) -> dict[str, str]:
    idx = kind.get("index")
    if not idx:
        return {}
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
        docs = documents(kind)
        index = index_rows(kind)
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
            if index:
                if fname not in index:
                    out.append({"key": f"{ref}:not_in_index", "detail": f"missing from {kind['index']['file']}"})
                else:
                    istate = normalize(index[fname], kind)
                    if state and istate and istate != state:
                        out.append({"key": f"{ref}:index_mismatch", "detail": f"file says {state}, index says {istate}"})
            need = kind.get("links", {}).get(state or "")
            if need and raw:
                targets = [need["file_prefix"].format(int(t) if t.isdigit() else t) for t in re.findall(need["pattern"], raw)]
                if not targets or not all(any(n.startswith(t) for n in docs) for t in targets):
                    out.append({"key": f"{ref}:missing_successor", "detail": f"{state} must name an existing successor ({need['pattern']})"})
            if since and state:
                old = subprocess.run(["git", "show", f"{since}:{path.relative_to(ROOT)}"], cwd=ROOT, capture_output=True, text=True)
                if old.returncode == 0:
                    old_state = normalize(status_text(old.stdout, kind["status"]), kind)
                    if old_state and not forward(kind, old_state, state):
                        out.append({"key": f"{ref}:backward:{old_state}->{state}", "detail": f"{old_state} → {state} is not a forward move ({kind['declared']})"})
        for fname in index:
            if fname not in docs:
                out.append({"key": f"{kid}:{fname}:index_without_file", "detail": f"{kind['index']['file']} lists a file that does not exist"})
    return out


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
    bad = []
    for i in issues:
        mine = sorted(lbl["name"] for lbl in i["labels"] if lbl["name"] in labels)
        if len(mine) != 1:
            bad.append(f"#{i['number']} {', '.join(mine) or '(no triage label)'}: {i['title'][:70]}")
    return f"{repo}: {len(issues)} open issues, {len(bad)} not in exactly one triage state" + ("".join(f"\n  {b}" for b in bad))


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
                print(f"docs-machine ok: {len(procs.get('skills', {}))} procedures, {vend} vendored pinned, lifecycles legal ({n} known defects baselined)")
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
        if argv[0] in ("run", "step", "escalate"):
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
