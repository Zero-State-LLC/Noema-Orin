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
            ("ORG_SUCCESSION_RULE", NOTICE["office_id"], None),
            ("LOOK", None, None)])
        designated = canon([{**NOTICE, "successor_handle": "Aphelia-Founder"}])
        self.assertEqual(refine_offices(opts[5:8], designated, HOME, HANDLES, "Aphelia-Founder"), [])

    def test_role_handles_from_cohort(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "shared").mkdir()
            (Path(d) / "shared" / "cohort.tsv").write_text("m03\tplayer.Rivet-Custodian\nzz\tplayer.x\n")
            self.assertEqual(role_handles(Path(d), {"m03": "custodian"}), {"custodian": "Rivet-Custodian"})


if __name__ == "__main__":
    unittest.main()
