import tempfile
import unittest
from pathlib import Path

from noema_orin.offices import CATALOG, duplicates, missing, refine_offices, retarget_create
from noema_orin.players import role_handles
from noema_orin.roles import DENY_ALWAYS, role_for

HOME = "org.reach-compact.34df3bb5"
HANDLES = {"founder": "Aphelia-Founder", "speaker": "Cantor-Speaker", "custodian": "Rivet-Custodian",
           "archivist": "Vellum-Archivist"}


def canon(offices):
    return {"organizations": [{"org_id": HOME, "my_role": "founder", "created_cycle": 1, "offices": offices}]}


NOTICE = {"office_id": "office.reach-compact.34df3bb5.notice.a", "display_name": "Notice", "status": "OCCUPIED",
          "holder_handle": "Cantor-Speaker", "authority_profile": "PUBLISH_NOTICE"}
DUP = {"office_id": "office.reach-compact.34df3bb5.notice.b", "display_name": "Notice", "status": "VACANT",
       "authority_profile": "PUBLISH_NOTICE"}
STEWARD = {"office_id": "office.reach-compact.34df3bb5.steward.c", "display_name": "Steward", "status": "VACANT",
           "authority_profile": "OPERATE_NAMED_ASSET"}


def opt(action, target, label=None, **raw):
    return {"action": action, "target_id": target, "target_label": label, "raw": {"operation": action, **raw}}


class CatalogTests(unittest.TestCase):
    def test_catalog_never_grants_denied_authority(self):
        profiles = {p for _n, p in CATALOG.values()}
        self.assertNotIn("OPERATE_RESOURCE_ACCOUNT", profiles)  # treasury TRADE
        self.assertNotIn("GRANT_ACCESS", profiles)
        self.assertIn("TRADE", DENY_ALWAYS)
        self.assertIn("ORG_OFFICE_RETIRE", role_for("founder")["allow"])

    def test_missing_offices_in_catalog_order(self):
        self.assertEqual([n for n, _ in missing(canon([NOTICE]), HOME)], ["Steward", "Archive Keeper"])
        self.assertEqual(missing(canon([NOTICE, STEWARD, {**STEWARD, "display_name": "Archive Keeper",
                                                          "office_id": "x"}]), HOME), [])

    def test_duplicate_keeps_occupied_office(self):
        self.assertEqual(duplicates(canon([DUP, NOTICE]), HOME), {DUP["office_id"]})
        self.assertEqual(duplicates(canon([NOTICE, {**DUP, "status": "RETIRED"}]), HOME), set())

    def test_create_is_retargeted_to_next_missing_profile(self):
        base = opt("ORG_OFFICE_CREATE", HOME, cmd=f'office create {HOME} name="Notice" profile=PUBLISH_NOTICE')
        out = retarget_create(base, canon([NOTICE]), HOME)
        self.assertIn('name="Steward" profile=OPERATE_NAMED_ASSET', out["raw"]["cmd"])
        full = [NOTICE, STEWARD, {**STEWARD, "display_name": "Archive Keeper", "office_id": "y"}]
        self.assertIsNone(retarget_create(base, canon(full), HOME))

    def test_create_args_reach_engine_fields(self):
        from importlib.util import find_spec
        if not find_spec("noema_client"):
            self.skipTest("needs noema-client")
        from noema_orin.orin_adapter import _proposal
        base = opt("ORG_OFFICE_CREATE", HOME, cmd=f'office create {HOME} name="Notice" profile=PUBLISH_NOTICE')
        args = _proposal(retarget_create(base, canon([NOTICE]), HOME), {}).arguments
        self.assertEqual((args["org_id"], args["display_name"], args["profile"]), (HOME, "Steward", "OPERATE_NAMED_ASSET"))

    def test_refine_seats_intended_holder_retires_dupes_and_names_cohort_heir(self):
        c = canon([NOTICE, DUP, STEWARD])
        opts = [opt("ORG_OFFICE_ASSIGN", STEWARD["office_id"], "Tallow-Quartermaster"),
                opt("ORG_OFFICE_ASSIGN", STEWARD["office_id"], "Rivet-Custodian"),
                opt("ORG_OFFICE_ASSIGN", DUP["office_id"], "Cantor-Speaker"),
                opt("ORG_OFFICE_RETIRE", NOTICE["office_id"]),
                opt("ORG_OFFICE_RETIRE", DUP["office_id"]),
                opt("ORG_SUCCESSION_DESIGNATE", NOTICE["office_id"], player_id="player.stranger"),
                opt("ORG_SUCCESSION_DESIGNATE", NOTICE["office_id"], player_id="player.Aphelia-Founder"),
                opt("ORG_SUCCESSION_RULE", NOTICE["office_id"]),
                {"action": "LOOK", "raw": {}}]
        out = refine_offices(opts, c, HOME, HANDLES, "Aphelia-Founder")
        got = [(o["action"], o.get("target_id"), o.get("target_label") or o["raw"].get("player_id")) for o in out]
        self.assertEqual(got, [
            ("ORG_OFFICE_ASSIGN", STEWARD["office_id"], "Rivet-Custodian"),
            ("ORG_OFFICE_RETIRE", DUP["office_id"], None),
            ("ORG_SUCCESSION_DESIGNATE", NOTICE["office_id"], "player.Aphelia-Founder"),
            ("LOOK", None, None)])
        designated = canon([{**NOTICE, "successor_handle": "Aphelia-Founder"}])
        self.assertEqual(refine_offices(opts[5:8], designated, HOME, HANDLES, "Aphelia-Founder"), [])
        no_heir = refine_offices([opt("ORG_SUCCESSION_RULE", NOTICE["office_id"])], c, HOME, HANDLES, "Aphelia-Founder")
        self.assertEqual([o["action"] for o in no_heir], ["ORG_SUCCESSION_RULE"])

    def test_role_handles_from_cohort(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "shared").mkdir()
            (Path(d) / "shared" / "cohort.tsv").write_text("m03\tplayer.Rivet-Custodian\nzz\tplayer.x\n")
            self.assertEqual(role_handles(Path(d), {"m03": "custodian"}), {"custodian": "Rivet-Custodian"})


if __name__ == "__main__":
    unittest.main()


class MenuPipelineTests(unittest.TestCase):
    def test_engine_notice_create_survives_as_steward_when_notice_exists(self):
        from noema_orin.orin_adapter import OrinAdapter

        a = OrinAdapter.__new__(OrinAdapter)
        a.allowed, a.cohort_ids, a.role_handles = frozenset(role_for("founder")["allow"]), set(), HANDLES
        a.builds, a.supply, a.verbs = None, None, set(role_for("founder")["verbs"])
        c = canon([NOTICE])
        c["affordances"] = [{"action": "ORG_OFFICE_CREATE", "operation": "ORG_OFFICE_CREATE", "available": True,
                             "target_id": HOME, "cmd": f'office create {HOME} name="Notice" profile=PUBLISH_NOTICE'}]
        menu = a._menu({"canonical": c})
        self.assertEqual([o["label"] for o in menu], ["Create Steward office"])


import importlib.util

_HAS_CLIENT = importlib.util.find_spec("noema_client") is not None


@unittest.skipUnless(_HAS_CLIENT, "requires noema_client")
class SupplyPickTests(unittest.TestCase):
    def test_empty_hold_custodian_harvests_offered_node(self):
        from noema_orin.orin_adapter import OrinAdapter

        a = OrinAdapter.__new__(OrinAdapter)
        spec = role_for("custodian")
        a.allowed, a.cohort_ids, a.role_handles = frozenset(spec["allow"]), set(), {}
        a.builds, a.supply, a.verbs = spec.get("builds"), spec.get("supply"), set(spec["verbs"])
        a.memory, a.world_map, a.dwell, a.explorer, a.default_args, a.stats_mem = None, None, 0, False, {}, 0
        c = {"resources": {"energy": 50, "attention": 1, "storage": 16}, "location": {"room_id": "room.civic-exchange"},
             "affordances": [{"action": "HARVEST", "operation": "HARVEST", "available": False, "target_id": "e.fab",
                              "reason": "Not enough stock available."},
                             {"action": "HARVEST", "operation": "HARVEST", "available": True, "target_id": "e.cache",
                              "cmd": "harvest Salvage Cache 1"},
                             {"action": "MOVE", "available": True, "dest": "room.archive"}]}
        options = a._menu({"canonical": c})
        p = a._plan({"canonical": c}, options)
        self.assertEqual((p.action, p.target_id), ("HARVEST", "e.cache"))

    def test_loaded_custodian_restores_when_offered(self):
        from noema_orin.orin_adapter import OrinAdapter

        a = OrinAdapter.__new__(OrinAdapter)
        spec = role_for("custodian")
        a.allowed, a.cohort_ids, a.role_handles = frozenset(spec["allow"]), set(), {}
        a.builds, a.supply, a.verbs = spec.get("builds"), spec.get("supply"), set(spec["verbs"])
        a.memory, a.world_map, a.dwell, a.explorer, a.default_args, a.stats_mem = None, None, 0, False, {}, 0
        c = {"resources": {"energy": 43, "attention": 0, "storage": 11}, "location": {"room_id": "room.relay-quarter"},
             "affordances": [{"action": "RESTORE", "operation": "RESTORE", "available": True, "target_id": "e.relay"},
                             {"action": "MOVE", "available": True, "dest": "room.archive"}]}
        p = a._plan({"canonical": c}, a._menu({"canonical": c}))
        self.assertEqual((p.action, p.target_id), ("RESTORE", "e.relay"))


class QuartermasterAndIdleTests(unittest.TestCase):
    def _qm(self):
        from noema_orin.orin_adapter import OrinAdapter

        a = OrinAdapter.__new__(OrinAdapter)
        spec = role_for("quartermaster")
        a.allowed, a.cohort_ids, a.role_handles = frozenset(spec["allow"]), set(), {}
        a.builds, a.supply, a.verbs = tuple(spec.get("builds") or ()), spec.get("supply"), set(spec["verbs"])
        a.memory, a.world_map, a.dwell, a.explorer, a.default_args, a.stats_mem = None, None, 0, False, {}, 0
        return a

    def test_full_hold_quartermaster_constructs_storage_bay(self):
        a = self._qm()
        c = {"resources": {"energy": 20, "attention": 8, "storage": 0}, "location": {"room_id": "room.civic-exchange"},
             "affordances": [{"action": "BUILD", "verb": "BUILD", "operation": "CONSTRUCT", "class": "storage_bay",
                              "available": True},
                             {"action": "BUILD", "verb": "BUILD", "operation": "CONSTRUCT", "class": "relay",
                              "available": True}]}
        p = a._plan({"canonical": c}, a._menu({"canonical": c}))
        self.assertEqual((p.action, p.arguments.get("class")), ("CONSTRUCT", "storage_bay"))

    def test_quartermaster_never_offered_trade(self):
        self.assertNotIn("TRADE", role_for("quartermaster")["allow"])

    def test_idle_menu_skips_model(self):
        from noema_orin.orin_adapter import OrinAdapter

        a = OrinAdapter.__new__(OrinAdapter)
        spec = role_for("founder")
        a.allowed, a.cohort_ids, a.role_handles, a.on_turn = frozenset(spec["allow"]), set(), {}, None
        a.builds, a.supply, a.verbs = (), None, set(spec["verbs"])
        a.memory, a.world_map, a.dwell, a.explorer, a.default_args, a.stats_mem = None, None, 5, False, {}, 0
        a.stats, a.recent, a.memories = {"planner": 0, "model": 0, "fallback": 0, "loop_break": 0}, [], []
        a.health = type("H", (), {"record_turn": lambda *x, **k: None})()
        a._ask = lambda *x: (_ for _ in ()).throw(AssertionError("model called on idle menu"))
        c = {"resources": {"energy": 60, "attention": 8, "storage": 16}, "location": {"room_id": "room.transit-ring"},
             "affordances": [{"action": "LOOK", "available": True}, {"action": "INSPECT", "available": True}]}
        p = a.decide({"canonical": c})
        self.assertEqual(p.action, "WAIT")
        self.assertEqual(a.stats["idle_skip"], 1)

    def test_full_hold_short_on_energy_waits_instead_of_harvesting(self):
        a = self._qm()
        c = {"resources": {"energy": 2, "attention": 8, "storage": 0}, "location": {"room_id": "room.civic-exchange"},
             "affordances": [{"action": "BUILD", "operation": "CONSTRUCT", "class": "storage_bay", "available": False,
                              "reason": "You do not have enough resources to construct."},
                             {"action": "HARVEST", "operation": "HARVEST", "available": True, "target_id": "e.c"}]}
        p = a._plan({"canonical": c}, a._menu({"canonical": c}))
        self.assertEqual(p.action, "WAIT")
