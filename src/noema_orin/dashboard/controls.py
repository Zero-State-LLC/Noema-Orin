"""Safe audited operator control plane for Noema-Orin dashboard (D3/#183).

Strictly bounded to allowlisted systemd user units, clamped RSI policy knobs, atomic
persona rollback, runtime inference/voice overrides (never touching tokens), stale
cohort claim release, and bounded maintenance ops. Every action is recorded in
`logs/dashboard-audit.jsonl` with zero secrets.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Protocol

from ..memory import WorldMap
from ..memory_sync import compact_map
from ..persona import rollback_to_version
from ..qualify import run_qualification
from ..rsi import RsiRatchet, atomic_write_json, atomic_write_text, clamp_knobs, load_agenda, save_agenda

ALLOWED_MEMBERS = ("m01", "m02", "m03", "m04", "m05", "m06")
ALLOWED_UNITS = (
    "noema-player@m01",
    "noema-player@m02",
    "noema-player@m03",
    "noema-player@m04",
    "noema-player@m05",
    "noema-player@m06",
    "noema-maint-patrol",
    "noema-llama-server",
    "noema-embed-server",
)
_UNIT_ACTIONS = frozenset({"start", "stop", "restart"})
_GROUP_ACTIONS = frozenset({"start", "stop", "rolling_restart"})
_OPS_JOBS = frozenset({"metrics", "memory_sync", "compact_map", "qualify"})


class SystemdRunner(Protocol):
    def unit_statuses(self, units: tuple[str, ...]) -> dict[str, dict[str, str]]: ...
    def unit_action(self, unit: str, action: str) -> tuple[bool, str]: ...
    def group_action(self, action: str, preset: str = "full") -> tuple[bool, str]: ...


class LiveSystemdRunner:
    """Real `systemctl --user` and `deploy/rolling-restart.sh` executor (shell=False always)."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parents[3]

    def unit_statuses(self, units: tuple[str, ...]) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {}
        for unit in units:
            try:
                res = subprocess.run(
                    ["systemctl", "--user", "show", unit, "--property=ActiveState,SubState,ActiveEnterTimestamp"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                kv = dict(line.split("=", 1) for line in res.stdout.splitlines() if "=" in line)
                out[unit] = {
                    "active_state": kv.get("ActiveState", "unknown"),
                    "sub_state": kv.get("SubState", "unknown"),
                    "since": kv.get("ActiveEnterTimestamp", ""),
                }
            except Exception:
                out[unit] = {"active_state": "unknown", "sub_state": "unknown", "since": ""}
        return out

    def unit_action(self, unit: str, action: str) -> tuple[bool, str]:
        if unit not in ALLOWED_UNITS or action not in _UNIT_ACTIONS:
            return False, "disallowed unit or action"
        res = subprocess.run(
            ["systemctl", "--user", action, unit],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        return res.returncode == 0, (res.stdout.strip() or res.stderr.strip() or f"{action} {unit}")

    def group_action(self, action: str, preset: str = "full") -> tuple[bool, str]:
        if action in ("start", "stop"):
            res = subprocess.run(
                ["systemctl", "--user", action, "noema-players.target"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            return res.returncode == 0, (res.stdout.strip() or res.stderr.strip() or f"group {action}")
        if action == "rolling_restart":
            script = self.repo_root / "deploy" / "rolling-restart.sh"
            if not script.is_file():
                return False, "rolling-restart.sh not found"
            env = dict(os.environ)
            if preset == "canary":
                env["UNITS"] = "noema-player@m02 noema-player@m06"
            res = subprocess.run(
                ["bash", str(script), "--apply"],
                capture_output=True,
                text=True,
                env=env,
                timeout=600,
                check=False,
            )
            tail = (res.stdout.splitlines() or res.stderr.splitlines() or ["done"])[-1]
            return res.returncode == 0, tail[:200]
        return False, "unknown group action"


class DashboardController:
    """Validated, mutex-guarded, audited operator controls (zero secrets, zero world writes)."""

    def __init__(
        self,
        *,
        root: Path,
        config_dir: Path,
        systemd_runner: SystemdRunner | None = None,
    ) -> None:
        self.root = Path(root)
        self.config_dir = Path(config_dir)
        self.systemd = systemd_runner if systemd_runner is not None else LiveSystemdRunner()
        self._ops_lock = threading.Lock()
        self._restart_lock = threading.Lock()

    def _audit(self, action: str, detail: dict[str, Any], ok: bool) -> None:
        logs = self.root / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": round(time.time(), 2),
            "action": action,
            "ok": bool(ok),
            "detail": detail,
        }
        with (logs / "dashboard-audit.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")

    def unit_control(self, unit: str, action: str) -> tuple[bool, dict[str, Any]]:
        if unit not in ALLOWED_UNITS or action not in _UNIT_ACTIONS:
            self._audit("unit:rejected", {"unit": str(unit)[:40], "action": str(action)[:20]}, False)
            return False, {"error": "unit or action not in allowlist"}
        ok, msg = self.systemd.unit_action(unit, action)
        self._audit(f"unit:{action}", {"unit": unit, "message": msg[:120]}, ok)
        return ok, {"ok": ok, "unit": unit, "action": action, "message": msg[:200]}

    def group_control(self, action: str, preset: str = "full") -> tuple[bool, dict[str, Any]]:
        if action not in _GROUP_ACTIONS or preset not in ("canary", "full"):
            self._audit("group:rejected", {"action": str(action)[:30], "preset": str(preset)[:20]}, False)
            return False, {"error": "invalid group action or preset"}
        if not self._restart_lock.acquire(blocking=False):
            return False, {"error": "group lifecycle action already in progress"}
        try:
            ok, msg = self.systemd.group_action(action, preset)
            self._audit(f"group:{action}", {"preset": preset, "message": msg[:120]}, ok)
            return ok, {"ok": ok, "action": action, "preset": preset, "message": msg[:200]}
        finally:
            self._restart_lock.release()

    def update_knobs(self, member: str, patch: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        if member not in ALLOWED_MEMBERS or not isinstance(patch, dict):
            return False, {"error": "invalid member or knob payload"}
        unknown = set(patch) - set(clamp_knobs({}).keys())
        if unknown:
            return False, {"error": f"unknown knob keys: {sorted(unknown)}"}
        mind = self.root / member / "mind"
        knobs_path = mind / "policy_knobs.json"
        current = json.loads(knobs_path.read_text(encoding="utf-8")) if knobs_path.is_file() else clamp_knobs({})
        merged = {**current, **patch}
        clamped = clamp_knobs(merged)
        atomic_write_json(knobs_path, clamped, mode=0o600)
        # Clear any open RSI canary so manual operator tuning is not misattributed to a model patch.
        ratchet = RsiRatchet(mind)
        if ratchet.state.get("candidate") is not None:
            ratchet.state["candidate"] = None
            ratchet.save()
        self._audit("knobs:update", {"member": member, "keys": sorted(patch.keys())}, True)
        return True, {"ok": True, "member": member, "knobs": clamped}

    def rsi_control(self, member: str, action: str) -> tuple[bool, dict[str, Any]]:
        if member not in ALLOWED_MEMBERS or action not in ("rollback", "pause", "resume", "clear_quarantine"):
            return False, {"error": "invalid member or rsi action"}
        mind = self.root / member / "mind"
        ratchet = RsiRatchet(mind)
        if action == "rollback":
            ver = int(ratchet.state.get("last_good_persona_version") or 1)
            restored = rollback_to_version(mind, ver)
            knobs = ratchet.state.get("last_good_knobs")
            if isinstance(knobs, dict):
                atomic_write_json(mind / "policy_knobs.json", clamp_knobs(knobs), mode=0o600)
            ratchet.state["candidate"] = None
            ratchet.save()
            self._audit("rsi:rollback", {"member": member, "version": ver}, restored is not None)
            return True, {"ok": True, "member": member, "restored_version": ver}
        if action == "pause":
            ratchet.state["paused"] = True
            ratchet.save()
            self._audit("rsi:pause", {"member": member}, True)
            return True, {"ok": True, "member": member, "paused": True}
        if action == "resume":
            ratchet.state["paused"] = False
            ratchet.save()
            self._audit("rsi:resume", {"member": member}, True)
            return True, {"ok": True, "member": member, "paused": False}
        qpath = mind / "quarantine.jsonl"
        if qpath.is_file():
            atomic_write_text(qpath, "", mode=0o600)
        self._audit("rsi:clear_quarantine", {"member": member}, True)
        return True, {"ok": True, "member": member, "quarantine_cleared": True}

    def set_runtime_mode(self, inference_mode: str, grounded_voice: bool) -> tuple[bool, dict[str, Any]]:
        mode = str(inference_mode or "").strip().lower()
        if mode not in ("cloud_first", "local_first"):
            return False, {"error": "inference_mode must be cloud_first or local_first"}
        gv = "1" if bool(grounded_voice) else "0"
        self.config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        content = (
            "# Managed by noema-dashboard (D-077); never stores tokens or credentials.\n"
            f"NOEMA_INFERENCE_MODE={mode}\n"
            f"NOEMA_GROUNDED_VOICE={gv}\n"
        )
        atomic_write_text(self.config_dir / "runtime-overrides.env", content, mode=0o600)
        self._audit("mode:update", {"inference_mode": mode, "grounded_voice": gv}, True)
        return True, {"ok": True, "inference_mode": mode, "grounded_voice": bool(grounded_voice)}

    def release_claim(self, target_id: str) -> tuple[bool, dict[str, Any]]:
        tid = str(target_id or "").strip()
        if not tid or len(tid) > 120:
            return False, {"error": "invalid target_id"}
        with WorldMap(self.root) as wm:
            wm.release_claim(tid)
        self._audit("claims:release", {"target_id": tid}, True)
        return True, {"ok": True, "released": tid}

    def refresh_agenda(self, member: str) -> tuple[bool, dict[str, Any]]:
        if member not in ALLOWED_MEMBERS:
            return False, {"error": "invalid member"}
        mind = self.root / member / "mind"
        ag = load_agenda(mind)
        ag["steps"] = []
        save_agenda(mind, ag)
        self._audit("agenda:refresh", {"member": member}, True)
        return True, {"ok": True, "member": member}

    def run_ops(self, job: str) -> tuple[bool, dict[str, Any]]:
        if job not in _OPS_JOBS:
            return False, {"error": "unknown ops job"}
        if not self._ops_lock.acquire(blocking=False):
            return False, {"error": "ops job already running"}
        try:
            if job == "compact_map":
                out = compact_map(self.root / "shared" / "map.db")
                self._audit("ops:compact_map", out, True)
                return True, {"ok": True, "job": job, "result": out}
            if job == "qualify":
                receipt = run_qualification()
                self._audit("ops:qualify", {"claim_label": receipt.get("claim_label")}, True)
                return True, {"ok": True, "job": job, "result": receipt}
            mod = "noema_orin.metrics" if job == "metrics" else "noema_orin.memory_sync"
            cmd = [sys.executable, "-m", mod, "--root", str(self.root)]
            if job == "metrics":
                cmd += ["--digest", "--hours", "24"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
            ok = res.returncode == 0
            tail = (res.stdout.splitlines() or res.stderr.splitlines() or [""])[-1][:300]
            self._audit(f"ops:{job}", {"rc": res.returncode}, ok)
            return ok, {"ok": ok, "job": job, "output": tail}
        finally:
            self._ops_lock.release()
