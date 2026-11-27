"""Persistent civic Player loop for one Orin member (D-009).

Needs the official ``noema-client`` (Python >=3.11) and an approved credential in the
member's own config dir. Runs bounded ``play`` sessions back to back until SIGTERM.
Decisions come from an OpenAI-compatible endpoint (local Ollama by default).
"""

import argparse
import json
import signal
import sys
import threading
from pathlib import Path

from .roles import DENY_ALWAYS, role_for
from .telemetry import rejection_summary, stop_detail


def build_policy(role: str):
    from noema_client.policy import ClientPolicy

    spec = role_for(role)
    if spec.get("operator"):
        return ClientPolicy(
            allow_trade=False,
            allow_trade_p2p=False,
            allow_shop_fulfill=False,
            allow_shop_manage=False,
            allow_agreement=False,
            allow_access=False,
            allow_contest=False,
            allow_contest_declare=False,
            allow_contest_defend=False,
            allow_items=False,
            allowed_actions=list(spec["allow"]),
            denied_actions=list(DENY_ALWAYS) + ["TRADE", "CONTEST_DEFEND"],
            max_consecutive_failures=3,
        )
    return ClientPolicy(
        allow_trade=False,
        allow_trade_p2p=False,
        allow_shop_fulfill=True,
        allow_shop_manage=(role == "quartermaster"),
        allow_agreement=True,
        allow_access=False,
        allow_contest=False,
        allow_contest_declare=False,
        allow_contest_defend=(role in ("surveyor", "archivist", "founder", "custodian")),
        allow_items=True,
        allowed_actions=list(spec["allow"]),
        denied_actions=list(DENY_ALWAYS),
        max_consecutive_failures=3,
    )


def member_phase_jitter(member: str, turn_gap: float) -> float:
    """Deterministic sub-gap phase jitter (T3/#157) to desynchronize 6 agents off cycle-head boundaries."""
    import hashlib

    digest = hashlib.sha256(str(member).encode("utf-8")).digest()
    frac = int.from_bytes(digest[:2], "big") / 65535.0
    span = max(0.5, min(3.5, float(turn_gap) * 0.35))
    return round(0.3 + frac * span, 1)


def stagger(
    members: list[str],
    member: str,
    cooldown: float,
    turn_gap: float,
    *,
    jitter_s: float = 0.0,
) -> tuple[float, float]:
    """Spread one shared model across the cohort: cooldown grows with cohort size, starts are offset."""
    n = max(1, len(members))
    cool = max(cooldown, turn_gap * n)
    idx = members.index(member) if member in members else 0
    return cool, round(idx * cool / n + float(jitter_s), 1)


def cohort_ids(root: Path) -> set[str]:
    """Player ids the Orin agents have observed for themselves (shared/cohort.tsv)."""
    path = root / "shared" / "cohort.tsv"
    if not path.exists():
        return set()
    return {line.split("\t")[1] for line in path.read_text().splitlines() if "\t" in line}


def role_handles(root: Path, roles: dict[str, str]) -> dict[str, str]:
    """role -> engine handle, from roles.tsv (member->role) and shared/cohort.tsv (member->player id)."""
    path = root / "shared" / "cohort.tsv"
    if not path.exists():
        return {}
    ids = dict(line.split("\t", 1) for line in path.read_text().splitlines() if "\t" in line)
    return {roles[m]: pid.strip().replace("player.", "", 1) for m, pid in ids.items() if m in roles}


def record_self(root: Path, member: str, player_id: str | None) -> None:
    if not player_id:
        return
    import fcntl
    from .rsi import atomic_write_text

    path = root / "shared" / "cohort.tsv"
    lock_path = root / "shared" / ".cohort.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock_fh:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        try:
            rows = dict(line.split("\t", 1) for line in path.read_text().splitlines() if "\t" in line) if path.exists() else {}
            if rows.get(member) != player_id:
                rows[member] = player_id
                atomic_write_text(path, "".join(f"{k}\t{v}\n" for k, v in sorted(rows.items())), mode=0o644)
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Persistent Orin civic Player")
    ap.add_argument("--member", required=True)
    ap.add_argument("--root", type=Path, default=Path.home() / "noema-players")
    ap.add_argument("--session-seconds", type=float, default=1800)
    ap.add_argument("--cooldown", type=float, default=20)
    ap.add_argument("--turn-gap", type=float, default=8, help="seconds of model time reserved per cohort member (T19)")
    ns = ap.parse_args(argv)
    roles = dict(line.split("\t") for line in (ns.root / "roles.tsv").read_text().split("\n") if "\t" in line)
    role = roles.get(ns.member)
    role_for(role)
    from noema_client.client import NoemaClient

    from .agenda import AgendaManager
    from .orin_adapter import from_env, reflect
    from .persona import apply_reflection, load_or_seed, prompt_block, rollback_to_version
    from .rsi import (
        RsiRatchet,
        apply_knob_deltas,
        atomic_write_json,
        build_session_dossier,
        load_agenda,
        load_or_init_knobs,
        maybe_revert_persona_on_epoch,
        save_agenda,
    )

    home = ns.root / ns.member
    mind = home / "mind"
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    spec = role_for(role)
    persona = load_or_seed(mind, role)
    knobs = load_or_init_knobs(mind, persona.get("traits"))
    agenda = load_agenda(mind)
    ratchet = RsiRatchet(mind)

    def system_brief() -> str:
        return (prompt_block(persona) + " Mission: " + str(spec["mission"]) +
                " Only these actions are permitted: " + ", ".join(spec["allow"]) + ".")

    adapter = from_env(system_brief())
    adapter.allowed = frozenset(spec["allow"])
    adapter.default_args = dict(spec.get("args") or {})
    adapter.verbs = set(spec["verbs"])
    adapter.supply = set(spec.get("supply") or ())
    adapter.builds = tuple(spec.get("builds") or ())
    adapter.focus_tracks = tuple(spec.get("focus_tracks") or ())
    adapter.health.role = f"{persona['name']}-{role}"
    adapter.explorer = role == "surveyor"
    adapter.policy_knobs = dict(knobs)
    adapter.persona_traits = dict(persona.get("traits") or {})
    adapter.mind_dir = mind
    adapter.agenda_manager = AgendaManager.from_disk(mind)
    adapter.held_tracks = list(agenda.get("held_tracks") or ([agenda["held_track"]] if agenda.get("held_track") else []))[-2:]
    if adapter.held_tracks:
        adapter.held_track = adapter.held_tracks[-1]
    if agenda.get("build_room"):
        adapter.build_room = agenda["build_room"]
    from .embedder import default_embedder
    from .memory import Memory, WorldMap

    adapter.memory, adapter.world_map = Memory(mind, embedder=default_embedder()), WorldMap(ns.root)
    from .transitions import TransitionLog

    adapter.transition_log = TransitionLog.from_env(mind)  # D-078: None unless NOEMA_TRANSITION_LOG=1
    from .consequence import attach_shadow, close_shadow_session

    # C3 (#198): shadow mode needs the transition log on and NOEMA_CONSEQUENCE_SHADOW=1. It only reports.
    try:
        attach_shadow(adapter, mind)
    except Exception as exc:
        print(json.dumps({"member": ns.member, "consequence_error": type(exc).__name__}), flush=True)

    def on_turn(pid):
        record_self(ns.root, ns.member, pid)
        adapter.role_handles = role_handles(ns.root, roles)
        from . import planner

        pin = ns.root / "shared" / "home_org"
        planner.PINNED_HOME = pin.read_text().strip() or None if pin.exists() else None
        return cohort_ids(ns.root)

    adapter.on_turn = on_turn
    members = sorted(roles)
    cooldown, offset = stagger(
        members, ns.member, ns.cooldown, ns.turn_gap, jitter_s=member_phase_jitter(ns.member, ns.turn_gap)
    )
    print(json.dumps({"member": ns.member, "stagger_offset_s": offset, "cooldown_s": cooldown}), flush=True)
    if stop.wait(offset):
        return 0
    print(json.dumps({"member": ns.member, "role": role, "persona": persona["name"], "persona_version": persona["version"]}), flush=True)
    while not stop.is_set():
        from . import ws

        client = NoemaClient(config_home=home, policy=build_policy(role), ws_connect=ws.connect)
        if not getattr(client, "_credential", None):
            print(json.dumps({"member": ns.member, "role": role, "status": "NO_CREDENTIAL"}), flush=True)
            return 3
        loop_breaks_before = int(adapter.stats.get("loop_break", 0))
        if adapter.transition_log is not None:
            adapter.transition_log.new_session()  # never pair turns across a reconnect or session boundary
        close_shadow_session(adapter, None)  # turns left by a dropped session: learn budgets from them, score nothing
        try:
            report = client.play(duration=ns.session_seconds, cooldown=cooldown, adapter=adapter)
        except (ConnectionError, EOFError, OSError) as exc:
            print(json.dumps({"member": ns.member, "transport_drop": type(exc).__name__, "retry_in_s": cooldown}), flush=True)
            client.close() if hasattr(client, "close") else None
            stop.wait(cooldown)
            continue
        except Exception as exc:  # websockets.ConnectionClosed* are not OSError subclasses
            if "ConnectionClosed" not in type(exc).__name__:
                raise
            print(json.dumps({"member": ns.member, "transport_drop": type(exc).__name__, "retry_in_s": cooldown}), flush=True)
            stop.wait(cooldown)
            continue
        line = report.as_dict()
        if adapter.transition_log is not None:
            # C1 (#196): label this session's logged turns from the client's results. Must never end the loop.
            try:
                adapter.transition_log.record_outcomes(report)
            except Exception as exc:
                print(json.dumps({"member": ns.member, "transition_log_error": type(exc).__name__}), flush=True)
        consequence = close_shadow_session(adapter, report)  # C3: score this session, then fold it into the model
        try:
            compacted = adapter.memory.compact() if adapter.memory is not None else 0
        except Exception:  # compaction must never end a session loop
            compacted = -1
        held_tracks = list(getattr(adapter, "held_tracks", None) or ([] if not getattr(adapter, "held_track", None) else [adapter.held_track]))
        if getattr(adapter, "agenda_manager", None) is not None:
            adapter.agenda_manager.save(
                mind,
                held_tracks=held_tracks,
                build_room=getattr(adapter, "build_room", None),
                updated_seq=adapter.health.last_source_sequence,
            )
        else:
            save_agenda(mind, {
                "held_track": held_tracks[-1] if held_tracks else None,
                "held_tracks": held_tracks,
                "build_room": getattr(adapter, "build_room", None),
                "epoch": agenda.get("epoch", 0),
                "steps": agenda.get("steps", []),
                "updated_seq": adapter.health.last_source_sequence,
            })
        persona, _reverted = maybe_revert_persona_on_epoch(
            mind, persona, ratchet, cycle=getattr(adapter, "last_cycle", None)
        )
        rej = rejection_summary(report)
        dossier = build_session_dossier(
            role=role,
            role_verbs=set(spec["verbs"]),
            turn_log=list(getattr(adapter, "turn_log", [])),
            rejections=rej,
            stop_reason=line.get("stop_reason"),
            loop_breaks=max(0, int(adapter.stats.get("loop_break", 0)) - loop_breaks_before),
            deep_time_seen=dict(getattr(adapter, "deep_time_seen", {})),
        )
        rsi_verdict = ratchet.evaluate_session(dossier, persona, knobs)
        accepted = False
        if rsi_verdict["verdict"] == "ROLLED_BACK":
            restored = rollback_to_version(mind, rsi_verdict["rollback_persona_version"])
            if restored is not None:
                persona = restored
            knobs = dict(rsi_verdict["rollback_knobs"])
            atomic_write_json(mind / "policy_knobs.json", knobs)
        elif ratchet.can_propose() and dossier["turns"] >= 5:
            patch = reflect(adapter, persona, adapter.recent, dossier=dossier, knobs=knobs)
            if isinstance(patch, dict):
                cand_knobs, knobs_ok = apply_knob_deltas(knobs, patch.get("knob_deltas"))
                if knobs_ok:
                    reg_ok, _sig = ratchet.register_candidate(patch, persona["version"] + 1)
                    if reg_ok:
                        valid_seqs = set(dossier.get("valid_sequences") or []) or None
                        persona, accepted = apply_reflection(mind, persona, patch, valid_sequences=valid_seqs)
                        if accepted:
                            knobs = cand_knobs
                            atomic_write_json(mind / "policy_knobs.json", knobs)
                        else:
                            ratchet.state["candidate"] = None
                            ratchet.save()
        adapter.policy_knobs = dict(knobs)
        adapter.persona_traits = dict(persona.get("traits") or {})
        adapter.turn_log = []
        adapter.set_brief(system_brief())
        print(json.dumps({"member": ns.member, "role": role, "actions": len(report),
                          "stop_reason": line.get("stop_reason"), "stop_detail": stop_detail(report),
                          "rejections": rej, "decisions": dict(adapter.stats),
                          "persona_version": persona["version"], "memories_recalled": adapter.stats_mem,
                          "health": adapter.health.summary(), "memory_compacted": compacted,
                          "reflection": "accepted" if accepted else "rejected", "rsi": rsi_verdict,
                          **({"consequence": consequence} if consequence is not None else {})},
                         default=str), flush=True)
        stop.wait(ns.cooldown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
