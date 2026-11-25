"""S12: one public record per subject."""
import unittest

from noema_orin.orin_adapter import _one_record_per_subject


def pub(i, subject):
    return {"i": i, "action": "RECONSTRUCT_PUBLISH", "raw": {"subject_ref": subject, "reconstruction_id": f"recon.{i}"}}


class OneRecordPerSubjectTests(unittest.TestCase):
    def test_collapses_drafts_of_one_subject(self):
        menu = [pub(0, "entity.salvage-cache"), pub(1, "entity.salvage-cache"), pub(2, "entity.relay"),
                {"i": 3, "action": "WAIT"}]
        out = _one_record_per_subject(menu, set())
        self.assertEqual([o["raw"].get("subject_ref") for o in out if o["action"] == "RECONSTRUCT_PUBLISH"],
                         ["entity.salvage-cache", "entity.relay"])
        self.assertEqual([o["i"] for o in out], [0, 1, 2])

    def test_published_subject_is_not_republished_or_reconstructed(self):
        menu = [pub(0, "entity.salvage-cache"),
                {"i": 1, "action": "RECONSTRUCT", "raw": {"subject_ref": "entity.salvage-cache"}},
                {"i": 2, "action": "RECONSTRUCT", "raw": {"subject_ref": "entity.relay"}}]
        out = _one_record_per_subject(menu, {"entity.salvage-cache"})
        self.assertEqual([(o["action"], o["raw"]["subject_ref"]) for o in out], [("RECONSTRUCT", "entity.relay")])


if __name__ == "__main__":
    unittest.main()
