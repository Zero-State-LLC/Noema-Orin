import tempfile
import unittest
from pathlib import Path

from noema_orin.offices import CATALOG, duplicates, missing, refine_offices, retarget_create
from noema_orin.players import role_handles
from noema_orin.orin_adapter import _options
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
        self.assertIn("OPERATE_RESOURCE_ACCOUNT", profiles)  # D-047 / RFC-0141: seated; P2P trade stays client-denied
        self.assertNotIn("GRANT_ACCESS", profiles)
        self.assertIn("TRADE_PROPOSE", DENY_ALWAYS)
        self.assertIn("ORG_OFFICE_RETIRE", role_for("founder")["allow"])

    def test_missing_offices_in_catalog_order(self):
        self.assertEqual([n for n, _ in missing(canon([NOTICE]), HOME)], ["Steward", "Archive Keeper", "Quartermaster"])
        self.assertEqual(missing(canon([NOTICE, STEWARD, {**STEWARD, "display_name": "Archive Keeper",
                                                          "office_id": "x"},
                                        {**STEWARD, "display_name": "Quartermaster", "office_id": "q"}]), HOME), [])

    def test_duplicate_keeps_occupied_office(self):
        self.assertEqual(duplicates(canon([DUP, NOTICE]), HOME), {DUP["office_id"]})
        self.assertEqual(duplicates(canon([NOTICE, {**DUP, "status": "RETIRED"}]), HOME), set())

    def test_create_is_retargeted_to_next_missing_profile(self):
        base = opt("ORG_OFFICE_CREATE", HOME, cmd=f'office create {HOME} name="Notice" profile=PUBLISH_NOTICE')
        out = retarget_create(base, canon([NOTICE]), HOME)
        self.assertIn('name="Steward" profile=OPERATE_NAMED_ASSET', out["raw"]["cmd"])
        full = [NOTICE, STEWARD, {**STEWARD, "display_name": "Archive Keeper", "office_id": "y"},
                {**STEWARD, "display_name": "Quartermaster", "office_id": "q"}]
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


@unittest.skipUnless(_HAS_CLIENT, "requires noema_client")
class OfficeChurnTests(unittest.TestCase):
    """D-066: observations without the home org's offices must never trigger an office create."""

    def test_no_create_when_org_list_missing(self):
        from noema_orin import planner

        planner.PINNED_HOME = HOME
        try:
            opt = {"action": "ORG_OFFICE_CREATE", "target_id": HOME, "raw": {"cmd": f'office create {HOME} name="Notice"'}}
            self.assertIsNone(retarget_create(opt, {"organizations": []}, HOME))
            self.assertIsNone(retarget_create(opt, {}, HOME))
        finally:
            planner.PINNED_HOME = None

    def test_no_create_when_same_name_exists_vacant(self):
        vacant = {**DUP}
        opt = {"action": "ORG_OFFICE_CREATE", "target_id": HOME, "raw": {"cmd": "x"}}
        self.assertNotEqual(retarget_create(opt, canon([vacant]), HOME), None)  # other catalog offices still missing
        out = retarget_create(opt, canon([vacant]), HOME)
        self.assertNotIn('name="Notice"', out["raw"]["cmd"])


@unittest.skipUnless(_HAS_CLIENT, "requires noema_client")
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
        # RFC-0141 §2: P2P TRADE_PROPOSE stays denied; storefront TRADE is strictly planner-only (_hidden_verbs).
        self.assertNotIn("TRADE_PROPOSE", role_for("quartermaster")["allow"])
        self.assertIn("TRADE", self._qm()._hidden_verbs())

    def _seated(self, storage=10, custodian_here=True):
        a = self._qm()
        a.recent, a.role_handles = [], {"custodian": "Rivet-Custodian"}
        affs = [{"action": "HARVEST", "verb": "COMMIT", "operation": "HARVEST", "target_id": "entity.node",
                 "acting_for": "org.c", "office_id": "office.c.1", "available": True}]
        if custodian_here:
            affs += [{"action": "SUPPLY", "verb": "COMMIT", "operation": "SUPPLY", "target_id": "player.Rivet-Custodian",
                      "player_id": "player.Rivet-Custodian", "resource": r, "acting_for": "org.c",
                      "office_id": "office.c.1", "available": True} for r in ("energy", "storage")]
        c = {"resources": {"energy": 20, "attention": 8, "storage": 0}, "location": {
                "room_id": "room.x", "entities": [{"entity_id": "entity.node", "stock_amount": 30}]},
             "organizations": [{"org_id": "org.c", "treasury": {"storage": storage}}], "affordances": affs}
        return a, c

    def test_d061_builds_from_vault_above_floor(self):
        a, c = self._seated(storage=20, custodian_here=False)
        c["affordances"].append({"action": "BUILD", "verb": "BUILD", "operation": "CONSTRUCT", "class": "generator",
                                 "acting_for": "org.c", "office_id": "office.c.1", "available": True})
        p = a._plan({"canonical": c}, _options(c, a.allowed))
        self.assertEqual((p.action, p.arguments.get("class"), p.arguments.get("acting_for")),
                         ("CONSTRUCT", "generator", "org.c"))
        c["organizations"][0]["treasury"]["storage"] = 8  # below floor: keep harvesting
        p = a._plan({"canonical": c}, _options(c, a.allowed))
        self.assertEqual(p.action, "HARVEST")

    def test_d062_waits_for_fuel_beside_treasury_build(self):
        a, c = self._seated(storage=20, custodian_here=False)
        c["resources"] = {"energy": 2, "attention": 8, "storage": 14}  # cargo aboard: WAIT refuels
        c["affordances"] = [{"action": "BUILD", "verb": "BUILD", "operation": "CONSTRUCT", "class": "generator",
                             "acting_for": "org.c", "office_id": "office.c.1", "available": False,
                             "reason": "You do not have enough resources to construct."}]
        p = a._plan({"canonical": c}, _options(c, a.allowed))
        self.assertEqual(p.action, "WAIT")

    def test_d063_gathers_fuel_then_returns_to_build_room(self):
        import tempfile
        from pathlib import Path
        from noema_orin.memory import WorldMap

        a, c = self._seated(storage=30, custodian_here=False)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        a.world_map = WorldMap(Path(tmp.name))
        a.world_map.observe("room.hall", "Hall", 1, ["room.x"], [])
        a.world_map.observe("room.x", "X", 2, ["room.hall"], ["HARVEST"])
        a.build_room = "room.hall"
        # in room.x with an empty hold: personal HARVEST for fuel, not the treasury harvest
        c["resources"] = {"energy": 4, "attention": 8, "storage": 16}
        c["location"]["room_id"] = "room.x"
        c["location"]["exits"] = [{"to_room_id": "room.hall", "direction": "north"}]
        c["affordances"].append({"action": "HARVEST", "verb": "COMMIT", "operation": "HARVEST",
                                 "target_id": "entity.node", "available": True})
        p = a._plan({"canonical": c}, _options(c, a.allowed))
        self.assertEqual(p.action, "HARVEST")
        self.assertFalse((p.arguments or {}).get("acting_for"))
        # D-064: harvestable here but short of energy 2: WAIT, don't walk off
        c["resources"] = {"energy": 1, "attention": 8, "storage": 16}
        c["affordances"][-1] = {"action": "HARVEST", "verb": "COMMIT", "operation": "HARVEST", "target_id": "entity.node",
                                "available": False, "reason": "You need energy 2 and compute 1 to harvest."}
        p = a._plan({"canonical": c}, _options(c, a.allowed))
        self.assertEqual(p.action, "WAIT")
        # loaded: head back to the build room
        c["resources"] = {"energy": 4, "attention": 8, "storage": 8}
        p = a._plan({"canonical": c}, _options(c, a.allowed))
        self.assertEqual((p.action, p.target_id), ("MOVE", "north"))

    def test_d047_supplies_custodian_cargo_first(self):
        a, c = self._seated()
        p = a._plan({"canonical": c}, _options(c, a.allowed))
        self.assertEqual((p.action, p.arguments.get("resource"), p.arguments.get("amount")), ("SUPPLY", "storage", 3))
        self.assertEqual(p.arguments.get("office_id"), "office.c.1")

    def test_d047_treasury_harvest_with_full_pack(self):
        a, c = self._seated(storage=60, custodian_here=False)
        p = a._plan({"canonical": c}, _options(c, a.allowed))
        self.assertEqual((p.action, p.arguments.get("acting_for"), p.arguments.get("amount")), ("HARVEST", "org.c", 4))

    def test_d047_no_repeat_supply_within_10_turns(self):
        a, c = self._seated()
        a.recent = [{"action": "SUPPLY", "target": "player.Rivet-Custodian"}]
        p = a._plan({"canonical": c}, _options(c, a.allowed))
        self.assertEqual(p.action, "HARVEST")

    def _peer(self, energy, free):
        from noema_orin.memory import WorldMap

        a, c = self._seated(custodian_here=False)
        a.world_map = WorldMap(Path(tempfile.mkdtemp()))
        a.cohort_ids = {"player.Cantor-Speaker"}
        a.world_map.locate("player.Cantor-Speaker", "room.x", energy, free, 1)
        c["affordances"].append({"action": "SUPPLY", "verb": "COMMIT", "operation": "SUPPLY", "available": True,
                                 "target_id": "player.Cantor-Speaker", "player_id": "player.Cantor-Speaker",
                                 "resource": "storage", "acting_for": "org.c", "office_id": "office.c.1"})
        return a, c

    def test_d048_stuck_peer_gets_cargo_fuel(self):
        a, c = self._peer(energy=1, free=16)
        p = a._plan({"canonical": c}, _options(c, a.allowed))
        self.assertEqual((p.action, p.target_id), ("SUPPLY", "player.Cantor-Speaker"))

    def test_d048_healthy_or_loaded_peer_not_supplied(self):
        for energy, free in ((20, 16), (1, 10)):
            a, c = self._peer(energy, free)
            self.assertEqual(a._plan({"canonical": c}, _options(c, a.allowed)).action, "HARVEST")

    def test_d048_loaded_custodian_not_supplied(self):
        from noema_orin.memory import WorldMap

        a, c = self._seated()
        a.world_map = WorldMap(Path(tempfile.mkdtemp()))
        a.world_map.locate("player.Rivet-Custodian", "room.x", 9, 4, 1)  # 12 aboard
        self.assertEqual(a._plan({"canonical": c}, _options(c, a.allowed)).action, "HARVEST")

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

    def test_idle_empty_hold_quartermaster_walks_to_harvest_room(self):
        import tempfile
        from pathlib import Path

        from noema_orin.memory import WorldMap

        a = self._qm()
        a.role_handles = {"founder": "Aphelia-Founder"}  # every live agent has these (players.on_turn)
        a.on_turn, a.recent, a.memories = None, [], []
        a.stats = {"planner": 0, "model": 0, "fallback": 0, "loop_break": 0}
        a.health = type("H", (), {"record_turn": lambda *x, **k: None})()
        a._ask = lambda *x: (_ for _ in ()).throw(AssertionError("model called"))
        with tempfile.TemporaryDirectory() as d:
            a.world_map = WorldMap(Path(d))
            a.world_map.observe("room.civic", "Civic", 1, ["room.gen"], ["HARVEST"])
            a.world_map.observe("room.gen", "Gen", 2, ["room.civic"], ["LOOK"])
            c = {"resources": {"energy": 5, "attention": 8, "storage": 16},
                 "location": {"room_id": "room.gen", "exits": [{"to_room_id": "room.civic", "direction": "west"}]},
                 "affordances": [{"action": "LOOK", "available": True}]}
            a.memory = None
            p = a.decide({"canonical": c})
            self.assertEqual((p.action, p.target_id), ("MOVE", "west"))

    def test_archivist_low_attention_waits(self):
        from noema_orin.orin_adapter import OrinAdapter

        a = OrinAdapter.__new__(OrinAdapter)
        spec = role_for("archivist")
        a.allowed, a.cohort_ids, a.role_handles = frozenset(spec["allow"]), set(), {}
        a.builds, a.supply, a.verbs = (), None, set(spec["verbs"])
        a.memory, a.world_map, a.dwell, a.explorer, a.default_args, a.stats_mem = None, None, 3, False, {}, 0
        c = {"resources": {"energy": 40, "attention": 1, "storage": 16}, "location": {"room_id": "room.transit-ring"},
             "affordances": [{"action": "MOVE", "available": True, "dest": "room.civic"}]}
        self.assertEqual(a._plan({"canonical": c}, a._menu({"canonical": c})).action, "WAIT")

    def test_archivist_inspects_new_entity_when_no_reconstruction(self):
        from noema_orin.orin_adapter import OrinAdapter

        a = OrinAdapter.__new__(OrinAdapter)
        spec = role_for("archivist")
        a.allowed, a.cohort_ids, a.role_handles = frozenset(spec["allow"]), set(), {}
        a.builds, a.supply, a.verbs = (), None, set(spec["verbs"])
        a.memory, a.world_map, a.dwell, a.explorer, a.default_args, a.stats_mem = None, None, 3, False, {}, 0
        a.recent = [{"action": "INSPECT", "target": "e.old"}]
        c = {"resources": {"energy": 2, "attention": 8, "storage": 16}, "location": {"room_id": "room.civic"},
             "affordances": [{"action": "INSPECT", "available": True, "target_id": "e.old"},
                             {"action": "INSPECT", "available": True, "target_id": "e.new"},
                             {"action": "MOVE", "available": True, "dest": "room.x"}]}
        p = a._plan({"canonical": c}, a._menu({"canonical": c}))
        self.assertEqual((p.action, p.target_id), ("INSPECT", "e.new"))


class HeldFocusTests(unittest.TestCase):
    def test_d049_held_track_not_reoffered(self):
        from noema_orin.planner import focus

        opts = [{"i": 0, "action": "FOCUS", "raw": {"track": "surveyor"}},
                {"i": 1, "action": "FOCUS", "raw": {"track": "explorer"}},
                {"i": 2, "action": "MOVE", "raw": {}}]
        out = focus(opts, {"FOCUS"}, "surveyor")
        self.assertEqual([o for o in out if o["action"] == "FOCUS"], [])
        self.assertEqual(len(focus(opts, {"FOCUS"}, None)), 3)  # nothing dropped without a held track


@unittest.skipUnless(_HAS_CLIENT, "requires noema_client")
class CustodianEnergyTests(unittest.TestCase):
    def _cust(self):
        from noema_orin.orin_adapter import OrinAdapter

        a = OrinAdapter.__new__(OrinAdapter)
        spec = role_for("custodian")
        a.allowed, a.cohort_ids, a.role_handles = frozenset(spec["allow"]), set(), {}
        a.builds, a.supply, a.verbs = spec.get("builds"), spec.get("supply"), set(spec["verbs"])
        a.memory, a.world_map, a.dwell, a.explorer, a.default_args, a.stats_mem = None, None, 0, False, {}, 0
        a.recent = []
        return a

    def _canon(self, energy):
        return {"resources": {"energy": energy, "attention": 8, "storage": 11}, "location": {"room_id": "room.x"},
                "affordances": [{"action": "MOVE", "available": True, "direction": "north", "dest": "room.y"}]}

    def test_d050_loaded_and_weak_waits(self):
        a = self._cust()
        c = self._canon(3)
        self.assertEqual(a._plan({"canonical": c}, a._menu({"canonical": c})).action, "WAIT")

    def test_d050_loaded_and_ready_does_not_wait(self):
        a = self._cust()
        c = self._canon(9)
        p = a._plan({"canonical": c}, a._menu({"canonical": c}))
        self.assertNotEqual(getattr(p, "action", None), "WAIT")


@unittest.skipUnless(_HAS_CLIENT, "requires noema_client")
class SupplyProposalTests(unittest.TestCase):
    def test_d051_supply_proposal_always_has_amount(self):
        from noema_orin.orin_adapter import _proposal

        p = _proposal({"action": "SUPPLY", "target_id": "player.b",
                       "raw": {"action": "SUPPLY", "operation": "SUPPLY", "player_id": "player.b", "resource": "storage",
                               "acting_for": "org.c", "office_id": "office.c.1"}}, {})
        self.assertEqual(p.arguments.get("amount"), 3)

    def test_d051_model_never_sees_supply(self):
        from noema_orin.orin_adapter import OrinAdapter

        a = OrinAdapter.__new__(OrinAdapter)
        a.recent, a.system, a.memories, seen = [], "", [], {}

        def chat(instruction, user, **kw):
            seen["user"] = user
            return {"choice": 0}
        a._chat, a.memory, a.default_args = chat, None, {}
        a._ask({"canonical": {}}, [{"i": 0, "action": "SUPPLY", "label": "Supply", "raw": {}},
                                    {"i": 1, "action": "HARVEST", "label": "Harvest", "raw": {}}])
        self.assertNotIn("SUPPLY", seen.get("user", ""))


class RouteVerbTests(unittest.TestCase):
    def test_d052_route_skips_ubiquitous_construct(self):
        from noema_orin.memory import WorldMap
        from noema_orin.orin_adapter import _route_verbs
        from noema_orin.planner import route

        self.assertEqual(_route_verbs({"REPAIR", "CONSTRUCT"}), {"REPAIR"})
        self.assertEqual(_route_verbs({"CONSTRUCT"}), {"CONSTRUCT"})
        m = WorldMap(Path(tempfile.mkdtemp()))
        m.observe("room.a", "A", 1, ["room.b", "room.c"], [])
        m.observe("room.b", "B", 2, ["room.a"], ["REPAIR"])
        m.observe("room.c", "C", 9, ["room.a"], ["CONSTRUCT"])
        c = {"location": {"room_id": "room.a", "exits": [{"to_room_id": "room.b", "direction": "east"},
                                                          {"to_room_id": "room.c", "direction": "west"}]}}
        self.assertEqual(route(c, m, _route_verbs({"REPAIR", "CONSTRUCT"}), explorer=False), "east")


@unittest.skipUnless(_HAS_CLIENT, "requires noema_client")
class FallbackHiddenTests(unittest.TestCase):
    """D-067: the founder's fallback messaged maint and tester; planner-only verbs are hidden from it too."""

    def test_founder_fallback_skips_message(self):
        from noema_orin.orin_adapter import OrinAdapter

        a = OrinAdapter.__new__(OrinAdapter)
        spec = role_for("founder")
        a.verbs, a.recent, a.default_args, a.memory = set(spec["verbs"]), [], {}, None

        class F:
            def decide(self, context):
                return "fallback-wait"

        a.fallback = F()
        opts = [{"action": "MESSAGE", "target_id": "player.reach-maint3", "raw": {}}]
        self.assertEqual(a._role_fallback({}, opts), "fallback-wait")

    def test_generic_fallback_message_becomes_wait(self):
        from noema_client.types import ActionProposal
        from noema_orin.orin_adapter import OrinAdapter

        a = OrinAdapter.__new__(OrinAdapter)
        a.verbs, a.recent, a.default_args, a.memory = set(role_for("founder")["verbs"]), [], {}, None

        class F:
            def decide(self, context):
                return ActionProposal(action="MESSAGE", target_id="player.reach-maint3")

        a.fallback = F()
        self.assertEqual(a._role_fallback({}, []).action, "WAIT")


class SurveyorWalksTests(unittest.TestCase):
    """D-069: FOCUS offered everywhere must not pin the surveyor in place."""

    def test_focus_offer_does_not_hold(self):
        from noema_orin.orin_adapter import STAY_EXEMPT, _offered_here

        c = {"affordances": [{"action": "FOCUS", "operation": "FOCUS", "available": True}]}
        spec = role_for("surveyor")
        self.assertFalse(_offered_here(c, set(spec["verbs"]) - STAY_EXEMPT))
        c["affordances"].append({"action": "CONNECT", "operation": "CONNECT", "available": True})
        self.assertTrue(_offered_here(c, set(spec["verbs"]) - STAY_EXEMPT))


class SupersedeOnceTests(unittest.TestCase):
    """D-070: one RECONSTRUCT_SUPERSEDE per subject, none once revised."""

    def test_one_per_subject(self):
        from noema_orin.orin_adapter import _one_record_per_subject

        menu = [{"action": "RECONSTRUCT_SUPERSEDE", "raw": {"subject_ref": "entity.relay-7"}, "i": i} for i in range(5)]
        menu.append({"action": "WAIT", "raw": {}, "i": 5})
        self.assertEqual([o["action"] for o in _one_record_per_subject(menu, set())], ["RECONSTRUCT_SUPERSEDE", "WAIT"])
        self.assertEqual([o["action"] for o in _one_record_per_subject(menu, {"revised:entity.relay-7"})], ["WAIT"])


class FallbackAllowlistTests(unittest.TestCase):
    """D-071: the generic fallback cannot pick verbs outside the role's allow list."""

    def test_speaker_never_leaves_org(self):
        from importlib.util import find_spec
        if not find_spec("noema_client"):
            self.skipTest("needs noema-client")
        from noema_client.types import ActionProposal
        from noema_orin.orin_adapter import OrinAdapter

        a = OrinAdapter.__new__(OrinAdapter)
        spec = role_for("speaker")
        a.verbs, a.allowed, a.recent, a.default_args, a.memory = set(spec["verbs"]), frozenset(spec["allow"]), [], {}, None

        class F:
            def decide(self, context):
                return ActionProposal(action="ORG_MEMBER_REMOVE", target_id="org.x")

        a.fallback = F()
        self.assertEqual(a._role_fallback({}, []).action, "WAIT")


class AgreementOnceTests(unittest.TestCase):
    """D-072: one AGREEMENT_FORM per party, none once offered."""

    def test_one_per_party(self):
        from noema_orin.orin_adapter import _one_record_per_subject

        menu = [{"action": "AGREEMENT_FORM", "target_id": "player.Cantor-Speaker",
                 "raw": {"player_id": "player.Cantor-Speaker", "agreement_type": t}, "i": i}
                for i, t in enumerate(("TRADE", "ACCESS", "TRADE"))]
        self.assertEqual(len(_one_record_per_subject(menu, set())), 1)
        self.assertEqual(_one_record_per_subject(menu, {"agreement:player.Cantor-Speaker"}), [])


class ArchivistRoamsTests(unittest.TestCase):
    """D-073: published-subject records do not hold the archivist in place."""

    def test_done_subject_does_not_hold(self):
        from noema_orin.orin_adapter import _offered_here

        c = {"affordances": [{"action": "RECONSTRUCT_PUBLISH", "operation": "RECONSTRUCT_PUBLISH",
                              "subject_ref": "entity.relay-7", "available": True}]}
        verbs = set(role_for("archivist")["verbs"])
        self.assertTrue(_offered_here(c, verbs))
        self.assertFalse(_offered_here(c, verbs, done={"entity.relay-7"}))
