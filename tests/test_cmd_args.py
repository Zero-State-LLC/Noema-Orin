import unittest

from noema_orin.orin_adapter import _cmd_args


class CmdArgsTests(unittest.TestCase):
    def test_office_create(self):
        raw = {"operation": "ORG_OFFICE_CREATE", "target_id": "org.reach-compact.34df3bb5",
               "cmd": 'office create org.reach-compact.34df3bb5 name="Notice" profile=PUBLISH_NOTICE'}
        self.assertEqual(_cmd_args(raw), {"org_id": "org.reach-compact.34df3bb5", "display_name": "Notice", "profile": "PUBLISH_NOTICE"})

    def test_invite(self):
        raw = {"operation": "ORG_MEMBER_ADD", "target_id": "org.x.1", "target_label": "Cantor-Speaker",
               "cmd": "invite Cantor-Speaker to org.x.1 role=member"}
        self.assertEqual(_cmd_args(raw), {"org_id": "org.x.1", "agent_id": "player.Cantor-Speaker", "role": "member"})

    def test_office_assign(self):
        raw = {"operation": "ORG_OFFICE_ASSIGN", "target_id": "office.reach-compact.34df3bb5.notice.f7d94849",
               "target_label": "Cantor-Speaker", "cmd": "office assign office.reach-compact.34df3bb5.notice.f7d94849 Cantor-Speaker"}
        out = _cmd_args(raw)
        self.assertEqual(out["office_id"], "office.reach-compact.34df3bb5.notice.f7d94849")
        self.assertEqual(out["org_id"], "org.reach-compact.34df3bb5")
        self.assertEqual(out["agent_id"], "player.Cantor-Speaker")

    def test_non_org_untouched(self):
        self.assertEqual(_cmd_args({"operation": "HARVEST", "cmd": "harvest x=1"}), {})


if __name__ == "__main__":
    unittest.main()
