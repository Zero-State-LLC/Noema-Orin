"""D-077 Dashboard tests: D1 state aggregator, D2 HTTP/SSE server, D3 audited controls, D4 UI contract, D5 systemd."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from noema_orin.dashboard.controls import ALLOWED_UNITS, DashboardController
from noema_orin.dashboard.server import create_dashboard_server
from noema_orin.dashboard.state import DashboardStateReader
from noema_orin.memory import Memory, WorldMap
from noema_orin.metrics import collect as collect_metrics, open_db as open_metrics_db, record_hw_sample
from noema_orin.persona import load_or_seed
from noema_orin.rsi import RsiRatchet, load_or_init_knobs, save_agenda


class _NoSysfs:
    def read_text(self, path: str) -> str:
        raise FileNotFoundError(path)


class _FakeSystemdRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.active: dict[str, str] = {u: "active" for u in ALLOWED_UNITS}

    def unit_statuses(self, units: tuple[str, ...]) -> dict[str, dict[str, str]]:
        return {
            u: {"active_state": self.active.get(u, "inactive"), "sub_state": "running" if self.active.get(u) == "active" else "dead", "since": "2026-11-27T00:00:00Z"}
            for u in units
        }

    def unit_action(self, unit: str, action: str) -> tuple[bool, str]:
        self.calls.append((action, unit))
        if action == "stop":
            self.active[unit] = "inactive"
        elif action in ("start", "restart"):
            self.active[unit] = "active"
        return True, f"{action} {unit} ok"

    def group_action(self, action: str, preset: str = "full") -> tuple[bool, str]:
        self.calls.append((f"group:{action}", preset))
        return True, f"group {action} ({preset}) ok"


def _seed_fleet_fixture(root: Path, cfg_dir: Path) -> None:
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / "shared").mkdir(parents=True, exist_ok=True)
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (root / "roles.tsv").write_text(
        "m01\tfounder\nm02\tquartermaster\nm03\tcustodian\nm04\tarchivist\nm05\tspeaker\nm06\tsurveyor\n"
    )
    (root / "shared" / "cohort.tsv").write_text(
        "m01\tplayer.Aphelia-Founder\nm02\tplayer.Tallow-Quartermaster\nm03\tplayer.Rivet-Custodian\n"
        "m04\tplayer.Vellum-Archivist\nm05\tplayer.Cantor-Speaker\nm06\tplayer.Perigee-Surveyor\n"
    )
    (root / "shared" / "home_org").write_text("org.reach-compact.34df3bb5\n")
    # Secret sentinel in env file — must NEVER appear in any API response or audit log!
    (cfg_dir / "m01.env").write_text("NOEMA_TOKEN=header.eyJleHAiOjIwMDAwMDAwMDAsInBsYXllcl9pZCI6InBsYXllci5BcGhlbGlhLUZvdW5kZXIifQ.SENTINEL_SECRET_JWT_999\n")

    with WorldMap(root) as wm:
        wm.observe("room.civic-exchange", "Civic Exchange", 500, ["room.relay-quarter"], ["TRADE", "RECHARGE"])
        wm.observe("room.relay-quarter", "Relay Quarter", 502, ["room.civic-exchange"], ["REPAIR", "ATTEST"])
        wm.locate("player.Aphelia-Founder", "room.civic-exchange", 14, 16, 501)
        wm.locate("player.Rivet-Custodian", "room.relay-quarter", 1, 10, 502)
        wm.observe_deep_time("room.relay-quarter", {"sequence": 502, "scars": [{"scar_id": "scar.1", "domain": "economic", "strength": 0.45}], "active_norms": {"harvest_pressure": 3}})
        wm.observe_shared_work(
            "room.relay-quarter",
            "player.Perigee-Surveyor",
            {"sequence": 502, "location": {"entities": [{"entity_id": "entity.relay-7", "infra_type": "relay", "condition": 42}]}},
        )
        wm.claim_target("entity.relay-7", "player.Rivet-Custodian", "REPAIR", current_seq=502, ttl=12)
        wm.observe_market_and_equipment(
            "room.civic-exchange",
            "player.Tallow-Quartermaster",
            {
                "sequence": 503,
                "location": {"entities": [{"entity_id": "entity.stall-1", "infra_type": "barter_stall", "condition": 96}]},
                "shop_listings": [
                    {
                        "listing_id": "list.1",
                        "stall_id": "entity.stall-1",
                        "listing_kind": "CORE_SWAP",
                        "offer_asset": {"kind": "ITEM", "predicate": {"archetype": "power_cell"}},
                        "ask_asset": {"kind": "ITEM", "predicate": {"archetype": "depleted_cell"}},
                        "fills_remaining": 1,
                    }
                ],
                "inventory": [{"item_id": "item.cut.1", "archetype": "plasma_cutter", "equip_slot": "TOOL_SLOT", "equipped_slot": "TOOL_SLOT", "condition": 88, "max_condition": 100}],
            },
        )

    for m, role in (("m01", "founder"), ("m02", "quartermaster"), ("m03", "custodian"), ("m04", "archivist"), ("m05", "speaker"), ("m06", "surveyor")):
        mind = root / m / "mind"
        p = load_or_seed(mind, role)
        load_or_init_knobs(mind, p["traits"])
        RsiRatchet(mind).save()
        save_agenda(mind, {"held_tracks": ["engineer", "artificer"] if m == "m03" else [], "epoch": 2, "steps": [{"goal_kind": "REPAIR_INFRA", "target_room": "room.relay-quarter", "status": "active"}], "updated_seq": 502})
        with Memory(mind) as mem:
            mem.remember("Relay Quarter relay-7 condition 42", kind="room", room="room.relay-quarter", sequence=502)
            mem.note_player("player.Tallow-Quartermaster", "supplied cargo", sign=1, sequence=500)

    (root / "logs" / "noema-player@m03.log").write_text(
        "\n".join(
            [
                json.dumps({"member": "m03", "role": "custodian", "persona": "Rivet", "persona_version": 1}),
                json.dumps({"turn": 1, "source": "planner", "action": "REPAIR", "target": "entity.relay-7", "room": "room.relay-quarter", "budgets": {"energy": 6, "attention": 8, "compute": 5, "storage": 12}}),
                json.dumps({"member": "m03", "role": "custodian", "actions": 1, "stop_reason": "duration_elapsed", "rejections": {"by_verb_code": {"MOVE:STALE_HEAD": 1}}, "health": {"workers_ai_calls": 2, "local_s1_calls": 8, "ollama_fallbacks": 0}}),
            ]
        )
        + "\n"
    )
    db = open_metrics_db(root)
    try:
        collect_metrics(root, db)
        record_hw_sample(db, {"gpu_load_pct": 38.0, "cpu_temp_c": 47.5, "gpu_temp_c": 49.0, "vdd_in_mw": 9800, "mem_avail_mib": 4100, "llama_tps": 27.5, "kv_cache_ratio": 0.19}, ts=1000.0)
    finally:
        db.close()


class DashboardEndToEndTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "noema-players"
        self.cfg = Path(self.tmp.name) / "cfg"
        _seed_fleet_fixture(self.root, self.cfg)
        self.runner = _FakeSystemdRunner()
        self.reader = DashboardStateReader(
            root=self.root, config_dir=self.cfg, systemd_runner=self.runner,
            llama_base_url="http://127.0.0.1:9/v1", sysfs_probe=_NoSysfs(),
        )
        self.controller = DashboardController(root=self.root, config_dir=self.cfg, systemd_runner=self.runner)

    def test_d1_snapshot_aggregates_fleet_map_economy_hw_and_never_leaks_secrets(self):
        # Hermetic: the real Orin's sysfs must not override the metrics.db fixture.
        snap = self.reader.snapshot()
        self.assertEqual(len(snap["agents"]), 6)
        m03 = next(a for a in snap["agents"] if a["member"] == "m03")
        self.assertEqual(m03["role"], "custodian")
        self.assertEqual(m03["held_tracks"], ["engineer", "artificer"])
        self.assertEqual(m03["room_id"], "room.relay-quarter")
        self.assertEqual(len(snap["map"]["rooms"]), 2)
        self.assertEqual(len(snap["map"]["listings"]), 1)
        self.assertEqual(len(snap["map"]["claims"]), 1)
        self.assertEqual(snap["hw"]["gpu_load_pct"], 38.0)
        self.assertEqual(snap["tokens"][0]["status"], "OK")
        # Secret JWT signature must NEVER appear anywhere in snapshot or agent detail
        dumped = json.dumps(snap) + json.dumps(self.reader.agent_detail("m03", query="relay"))
        self.assertNotIn("SENTINEL_SECRET_JWT_999", dumped)
        # Incremental log tail: first poll starts at EOF (no history replay), then emits appended turns
        self.assertEqual(self.reader.poll_new_turns(), [])
        log = next((self.root / "logs").glob("noema-player@m*.log"))
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"turn": 999, "source": "planner", "action": "WAIT"}) + "\n")
        events = self.reader.poll_new_turns()
        self.assertEqual([e["turn"] for e in events], [999])
        self.assertEqual(self.reader.poll_new_turns(), [])
        # A second viewer with its own offsets is independent and also starts live
        other: dict[str, int] = {}
        self.assertEqual(self.reader.poll_new_turns(other), [])

    def test_c4_snapshot_carries_shadow_accuracy_only_for_members_that_have_it(self):
        log = self.root / "logs" / "noema-player@m03.log"
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"member": "m03", "role": "custodian", "actions": 10, "stop_reason": "duration_elapsed",
                                 "consequence": {"label": "INFERRED", "turns": 10, "no_prediction": 2, "by_verb": {
                                     "REPAIR": {"turns": 10, "predicted": 8, "tp": 3, "fp": 1, "fn": 1, "tn": 3}}}}) + "\n")
        db = open_metrics_db(self.root)
        try:
            collect_metrics(self.root, db)
        finally:
            db.close()
        snap = self.reader.snapshot()
        m03 = next(a for a in snap["agents"] if a["member"] == "m03")
        m01 = next(a for a in snap["agents"] if a["member"] == "m01")
        self.assertEqual(m03["consequence"]["label"], "INFERRED")
        self.assertEqual(m03["consequence"]["rejection_precision"], 0.75)
        self.assertEqual(m03["consequence"]["predictions"], 8)
        self.assertIsNone(m01["consequence"])  # shadow off for m01: no data, not zeros
        repo = Path(__file__).resolve().parents[1]
        app_js = (repo / "src/noema_orin/dashboard/static/app.js").read_text(encoding="utf-8")
        self.assertIn("a.consequence", app_js)
        self.assertIn("INFERRED", app_js)
        self.assertNotIn("innerHTML", app_js)

    def test_d2_d3_http_server_enforces_auth_and_audited_safe_controls(self):
        srv = create_dashboard_server(
            host="127.0.0.1",
            port=0,
            reader=self.reader,
            controller=self.controller,
            read_token="read-tok-1",
            control_token="ctrl-tok-2",
        )
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        base = f"http://127.0.0.1:{srv.server_address[1]}"

        # 0. Static UI and /api/health are reachable without auth
        with urllib.request.urlopen(base + "/api/health", timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            self.assertTrue(json.loads(resp.read().decode())["ok"])
        with urllib.request.urlopen(base + "/", timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("NOEMA · ORIN CONTROL", resp.read().decode("utf-8"))
        with urllib.request.urlopen(base + "/static/app.js", timeout=3) as resp:
            self.assertEqual(resp.status, 200)

        # 1. Unauthenticated /api/snapshot -> 401
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(base + "/api/snapshot", timeout=3)
        self.assertEqual(ctx.exception.code, 401)

        # 2. Read token accesses /api/snapshot -> 200, but CANNOT call POST /api/control/unit -> 403
        req_snap = urllib.request.Request(base + "/api/snapshot", headers={"Authorization": "Bearer read-tok-1"})
        with urllib.request.urlopen(req_snap, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            body = json.loads(resp.read().decode())
            self.assertEqual(len(body["agents"]), 6)

        req_forbid = urllib.request.Request(
            base + "/api/control/unit",
            data=json.dumps({"unit": "noema-player@m03", "action": "restart"}).encode(),
            headers={"Authorization": "Bearer read-tok-1", "Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx2:
            urllib.request.urlopen(req_forbid, timeout=3)
        self.assertEqual(ctx2.exception.code, 403)

        # 3. Control token restarts allowlisted unit -> 200, rejects non-allowlisted / shell injection -> 400
        req_ok = urllib.request.Request(
            base + "/api/control/unit",
            data=json.dumps({"unit": "noema-player@m03", "action": "restart"}).encode(),
            headers={"Authorization": "Bearer ctrl-tok-2", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_ok, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
        self.assertIn(("restart", "noema-player@m03"), self.runner.calls)

        req_bad_unit = urllib.request.Request(
            base + "/api/control/unit",
            data=json.dumps({"unit": "sshd; rm -rf /", "action": "restart"}).encode(),
            headers={"Authorization": "Bearer ctrl-tok-2", "Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx3:
            urllib.request.urlopen(req_bad_unit, timeout=3)
        self.assertEqual(ctx3.exception.code, 400)

        # 4. Knob updates clamp to KNOB_SPECS and persist atomically; inference mode writes runtime-overrides.env
        req_knob = urllib.request.Request(
            base + "/api/control/knobs/m03",
            data=json.dumps({"energy_reserve_floor": 99, "shop_margin_bias": -9}).encode(),
            headers={"Authorization": "Bearer ctrl-tok-2", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_knob, timeout=3) as resp:
            kdata = json.loads(resp.read().decode())
            self.assertEqual(kdata["knobs"]["energy_reserve_floor"], 5)  # clamped to max
            self.assertEqual(kdata["knobs"]["shop_margin_bias"], -1)     # clamped to min

        req_mode = urllib.request.Request(
            base + "/api/control/mode",
            data=json.dumps({"inference_mode": "local_first", "grounded_voice": True}).encode(),
            headers={"Authorization": "Bearer ctrl-tok-2", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_mode, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
        overrides = (self.cfg / "runtime-overrides.env").read_text()
        self.assertIn("NOEMA_INFERENCE_MODE=local_first", overrides)
        self.assertIn("NOEMA_GROUNDED_VOICE=1", overrides)

        # 5. Claim release removes cohort_claims row, RSI pause/resume honors RsiRatchet.can_propose(), agenda refresh & ops work, audit has zero secrets
        req_rel = urllib.request.Request(
            base + "/api/control/claims/release",
            data=json.dumps({"target_id": "entity.relay-7"}).encode(),
            headers={"Authorization": "Bearer ctrl-tok-2", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_rel, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
        self.assertEqual(self.reader.snapshot()["map"]["claims"], [])

        req_pause = urllib.request.Request(
            base + "/api/control/rsi/m03",
            data=json.dumps({"action": "pause"}).encode(),
            headers={"Authorization": "Bearer ctrl-tok-2", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_pause, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
        self.assertFalse(RsiRatchet(self.root / "m03" / "mind").can_propose())

        req_resume = urllib.request.Request(
            base + "/api/control/rsi/m03",
            data=json.dumps({"action": "resume"}).encode(),
            headers={"Authorization": "Bearer ctrl-tok-2", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_resume, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
        self.assertTrue(RsiRatchet(self.root / "m03" / "mind").can_propose())

        req_ag = urllib.request.Request(
            base + "/api/control/agenda/m03",
            data=b"{}",
            headers={"Authorization": "Bearer ctrl-tok-2", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_ag, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
        self.assertEqual(self.reader.agent_detail("m03")["agenda"]["steps"], [])

        req_grp = urllib.request.Request(
            base + "/api/control/group",
            data=json.dumps({"action": "rolling_restart", "preset": "canary"}).encode(),
            headers={"Authorization": "Bearer ctrl-tok-2", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_grp, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
        self.assertIn(("group:rolling_restart", "canary"), self.runner.calls)

        req_ops = urllib.request.Request(
            base + "/api/control/ops",
            data=json.dumps({"job": "compact_map"}).encode(),
            headers={"Authorization": "Bearer ctrl-tok-2", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_ops, timeout=3) as resp:
            self.assertEqual(resp.status, 200)

        audit = (self.root / "logs" / "dashboard-audit.jsonl").read_text()
        self.assertIn("unit:restart", audit)
        self.assertIn("rsi:pause", audit)
        self.assertIn("group:rolling_restart", audit)
        self.assertNotIn("ctrl-tok-2", audit)

    def test_d4_d5_hallmark_ui_safety_and_systemd_hardening(self):
        repo = Path(__file__).resolve().parents[1]
        app_js = (repo / "src/noema_orin/dashboard/static/app.js").read_text(encoding="utf-8")
        styles = (repo / "src/noema_orin/dashboard/static/styles.css").read_text(encoding="utf-8")
        # Hallmark / NOEMA VISUAL-DESIGN safety: never assign innerHTML on untrusted data
        self.assertNotIn("innerHTML", app_js)
        # Official noema-ledger-dark chamber tokens present
        for tok in ("#0E1114", "#161B20", "#E8E4DC", "#3DDCFF", "#C6FF3D", "#FF4D2E"):
            self.assertIn(tok, styles)
        # Systemd units enforce safe loopback default & tight RAM ceiling
        dash_unit = (repo / "deploy/systemd/noema-dashboard.service").read_text(encoding="utf-8")
        self.assertIn("127.0.0.1", dash_unit)
        self.assertIn("MemoryMax=96M", dash_unit)
        kiosk_unit = (repo / "deploy/jetson/noema-dashboard-kiosk.service").read_text(encoding="utf-8")
        # #190 replaced the Chromium `--kiosk` launcher with xinit + WebKit2GTK (kiosk-xinitrc -> kiosk.py).
        self.assertIn("deploy/jetson/kiosk-xinitrc", kiosk_unit)
        self.assertIn("MemoryMax=", kiosk_unit)
        xinitrc = (repo / "deploy/jetson/kiosk-xinitrc").read_text(encoding="utf-8")
        self.assertIn("deploy/jetson/kiosk.py", xinitrc)

    def test_d6_cached_snapshot_role_spark_and_alert_levels(self):
        from noema_orin.dashboard.state import classify_alerts

        a = self.reader.cached_snapshot(ttl=60)
        b = self.reader.cached_snapshot(ttl=60)
        self.assertIs(a, b)  # N viewers inside one TTL share one build
        self.assertTrue(a["map_sig"])
        m03 = next(x for x in a["agents"] if x["member"] == "m03")
        self.assertEqual(m03["role_spark"], [1])  # fixture turn is REPAIR, a custodian verb
        self.assertEqual(m03["turns_since_role"], 0)
        self.assertTrue(m03["last_role_action"].startswith("REPAIR"))
        self.assertIn("embedding_count", m03)

        items = classify_alerts(
            ["m01: idle_rate 0.9", "m02: rsi_rollback (regression)", "m03: 2/5 sessions ended early"],
            hw={"mem_avail_mib": 700},
            units={"noema-embed-server": {"active_state": "failed"}, "noema-player@m04": {"active_state": "inactive"}},
        )
        levels = {i["text"]: i["level"] for i in items}
        self.assertEqual(levels["m01: idle_rate 0.9"], "expected")
        self.assertEqual(levels["m02: rsi_rollback (regression)"], "crit")
        self.assertEqual(levels["m03: 2/5 sessions ended early"], "warn")
        self.assertEqual(levels["RAM available 700 MiB (< 1024)"], "warn")
        self.assertEqual(levels["noema-embed-server failed"], "crit")
        self.assertFalse(any("m04" in t for t in levels))  # players have their own card state

    def test_d7_stream_sends_map_once_and_omits_recent_turns(self):
        import socket
        import threading as _th

        srv = create_dashboard_server(host="127.0.0.1", port=0, reader=self.reader, controller=self.controller)
        t = _th.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            port = srv.server_address[1]
            s = socket.create_connection(("127.0.0.1", port), timeout=15)
            s.sendall(b"GET /api/stream?interval=2 HTTP/1.1\r\nHost: x\r\n\r\n")
            buf = b""
            deadline = time.monotonic() + 12
            while buf.count(b"event: snapshot") < 2 and time.monotonic() < deadline:
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
            s.close()
            snaps = [json.loads(part.split(b"data: ", 1)[1].split(b"\n", 1)[0])
                     for part in buf.split(b"event: snapshot\n")[1:3]]
            self.assertEqual(len(snaps), 2)
            self.assertIn("map", snaps[0])
            self.assertNotIn("map", snaps[1])  # unchanged map is not resent
            self.assertNotIn("recent_turns", snaps[0])
            self.assertEqual(snaps[0]["map_sig"], snaps[1]["map_sig"])
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
