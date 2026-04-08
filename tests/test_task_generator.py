import unittest

from os_simulator.task_generator import TaskGenerator


class TaskGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = TaskGenerator()

    def test_supported_task_types(self) -> None:
        for task_type in ("easy", "medium", "hard", "easy_1", "easy_2", "medium_1", "medium_2", "hard_1", "hard_2", "hard_3"):
            state, meta = self.generator.generate(task_type)
            self.assertIsNotNone(state)
            self.assertIn(meta["difficulty"], ("easy", "medium", "hard"))
            for required in ("task_id", "description", "difficulty", "expected_fixes", "success_conditions"):
                self.assertIn(required, meta)

    def test_determinism_for_same_task(self) -> None:
        state_a, meta_a = self.generator.generate("hard")
        state_b, meta_b = self.generator.generate("hard")

        self.assertEqual(meta_a, meta_b)
        self.assertEqual(state_a.resources.cpu, state_b.resources.cpu)
        self.assertEqual(state_a.resources.memory, state_b.resources.memory)
        self.assertEqual(state_a.resources.disk, state_b.resources.disk)
        self.assertEqual(
            [(p.pid, p.name, p.cpu_usage, p.status) for p in state_a.processes],
            [(p.pid, p.name, p.cpu_usage, p.status) for p in state_b.processes],
        )
        self.assertEqual(
            {name: svc.status for name, svc in state_a.services.items()},
            {name: svc.status for name, svc in state_b.services.items()},
        )

    def test_easy_state_has_simple_service_issue(self) -> None:
        state, _ = self.generator.generate("easy")
        self.assertEqual("stopped", state.services["nginx"].status)
        self.assertEqual("running", state.services["mysql"].status)

    def test_medium_state_has_invalid_config_and_failed_service(self) -> None:
        state, _ = self.generator.generate("medium")
        self.assertEqual("failed", state.services["nginx"].status)
        self.assertIn("INVALID", state.filesystem["/etc/nginx/nginx.conf"].content)
        self.assertTrue(any("invalid config" in log for log in state.logs))

    def test_hard_state_has_multiple_failures(self) -> None:
        state, _ = self.generator.generate("hard")
        self.assertGreater(state.resources.disk, 95.0)
        self.assertTrue(any(p.pid == 909 for p in state.processes))
        self.assertEqual("failed", state.services["nginx"].status)
        self.assertTrue(any("disk usage above 95%" in log for log in state.logs))

    def test_variants_are_distinct_and_deterministic(self) -> None:
        state_e1, meta_e1 = self.generator.generate("easy_1")
        state_e2, meta_e2 = self.generator.generate("easy_2")
        self.assertNotEqual(meta_e1["task_id"], meta_e2["task_id"])
        self.assertNotEqual({k: v.status for k, v in state_e1.services.items()}, {k: v.status for k, v in state_e2.services.items()})

        hard_a_state, hard_a_meta = self.generator.generate("hard_3")
        hard_b_state, hard_b_meta = self.generator.generate("hard_3")
        self.assertEqual(hard_a_meta, hard_b_meta)
        self.assertEqual(hard_a_state.resources.disk, hard_b_state.resources.disk)
        self.assertEqual(hard_a_state.resources.cpu, hard_b_state.resources.cpu)


if __name__ == "__main__":
    unittest.main()
