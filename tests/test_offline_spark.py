"""T6 (#6): offline Spark target isolation, both directions fail closed (ADR-013)."""
from __future__ import annotations

import unittest

from noema_orin import official_isolated as hosted
from noema_orin import offline_spark as spark

CHAMBER_TOKEN = "spark_" + "a" * 24
HOSTED_JWT = "aaa.bbb.ccc"


class ChamberAdmissionTests(unittest.TestCase):
    def test_valid_target(self):
        t = spark.OfflineSparkTarget.admit(origin="http://192.168.1.50:8080",
                                           world_id="offline.spark.lab-1", token=CHAMBER_TOKEN)
        self.assertEqual(t.world_id, "offline.spark.lab-1")
        self.assertNotIn(CHAMBER_TOKEN, repr(t))
        spark.admit_chamber_origin("http://127.0.0.1:9000")

    def test_hosted_inputs_are_refused_by_the_chamber(self):
        for origin in ("https://noema.guru:443", "https://api.noema.guru:443", "http://8.8.8.8:80",
                       "http://spark.local:8080", "http://169.254.1.1:80", "http://0.0.0.0:80",
                       "http://10.0.0.2:80/v1", "http://u:p@10.0.0.2:80", "ftp://10.0.0.2:21",
                       "http://10.0.0.2"):
            with self.assertRaises(ValueError, msg=origin):
                spark.admit_chamber_origin(origin)
        for world in ("world-01", "world.perihelion-reach", "test.hosted-canonical.x",
                      "offline.spark.", "offline.spark..x", "spark.x", ""):
            with self.assertRaises(ValueError, msg=world):
                spark.admit_chamber_world(world)
        for token in (HOSTED_JWT, "", "spark_short", "plain-secret"):
            with self.assertRaises(ValueError, msg=token):
                spark.admit_chamber_token(token)


class HostedRefusesChamberTests(unittest.TestCase):
    def test_hosted_wrapper_refuses_chamber_world_origin_and_token(self):
        with self.assertRaises(ValueError):
            hosted.admit_world("offline.spark.lab-1")
        common = dict(client_factory=object, client_version="0.2.0")
        with self.assertRaises(ValueError):
            hosted.OfficialIsolatedClient(world_id="test.hosted-canonical.x",
                                          controller_token=CHAMBER_TOKEN, admin_jwt=HOSTED_JWT, **common)
        with self.assertRaises(ValueError):
            hosted.OfficialIsolatedClient(world_id="test.hosted-canonical.x", server="http://192.168.1.50:8080",
                                          controller_token=HOSTED_JWT, admin_jwt=HOSTED_JWT, **common)


class ResearchReceiptTests(unittest.TestCase):
    def setUp(self):
        self.t = spark.OfflineSparkTarget.admit(origin="http://127.0.0.1:9000",
                                                world_id="offline.spark.lab-1", token=CHAMBER_TOKEN)

    def test_receipts_are_labelled_and_not_promotable(self):
        r = spark.research_receipt(self.t, status="ATTEMPTED", command_latency_ms=12.0)
        self.assertEqual(r["evidence_scope"], "OFFLINE_SPARK_RESEARCH")
        self.assertIs(r["promotable"], False)
        self.assertIn("0013-offline-spark", r["decision"])
        with self.assertRaises(ValueError):
            spark.assert_not_promotable(r)
        spark.assert_not_promotable({"world_id": "world-01", "evidence_scope": "PHYSICAL_ORIN_QUALIFICATION"})

    def test_receipts_refuse_strong_labels_and_secrets(self):
        with self.assertRaises(ValueError):
            spark.research_receipt(self.t, status="ATTEMPTED", claim_label="CANONICAL")
        for bad in ({"auth_header": "x"}, {"token": "x"}, {"evidence_scope": "HOSTED"}):
            with self.assertRaises(ValueError):
                spark.research_receipt(self.t, status="ATTEMPTED", **bad)


if __name__ == "__main__":
    unittest.main()
