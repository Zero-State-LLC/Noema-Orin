import unittest

from noema_orin.health import RoleHealthTracker, WorkersAICircuitBreaker


class HealthTelemetryTests(unittest.TestCase):
    def test_circuit_breaker_opens_and_recovers(self) -> None:
        cb = WorkersAICircuitBreaker(failure_threshold=2, cooldown_seconds=30.0)
        self.assertTrue(cb.allow_remote(100.0))
        self.assertFalse(cb.record_failure(100.0))
        self.assertTrue(cb.allow_remote(101.0))
        self.assertTrue(cb.record_failure(102.0))
        self.assertFalse(cb.allow_remote(120.0))
        self.assertTrue(cb.allow_remote(132.0))
        cb.record_success()
        self.assertEqual(cb.consecutive_failures, 0)

    def test_role_health_summary_ratios(self) -> None:
        tracker = RoleHealthTracker(role="Rivet-Custodian")
        tracker.record_turn(verb="GATHER", used_workers_ai=True, source_sequence=10)
        tracker.record_turn(verb="BUILD", used_workers_ai=True, source_sequence=11)
        tracker.record_turn(verb="WAIT", used_workers_ai=False, source_sequence=12, had_error=True)
        summary = tracker.summary()
        self.assertEqual(summary["total_turns"], 3)
        self.assertEqual(summary["active_turns"], 2)
        self.assertEqual(summary["idle_turns"], 1)
        self.assertAlmostEqual(summary["idle_ratio"], 0.333)
        self.assertAlmostEqual(summary["fallback_ratio"], 0.333)
        self.assertEqual(summary["error_count"], 1)
        self.assertEqual(summary["last_source_sequence"], 12)


if __name__ == "__main__":
    unittest.main()
