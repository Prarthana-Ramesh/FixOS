import unittest
from copy import deepcopy

from os_simulator.task_scoring import grade_easy, grade_hard, grade_medium
from os_simulator.models import Action
from os_simulator.reward import compute_dense_reward
from os_simulator.task_generator import TaskGenerator


class GradersAndRewardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = TaskGenerator()

    def test_easy_grader_binary(self) -> None:
        state, metadata = self.generator.generate("easy")
        score_before = grade_easy(state, state.history, metadata)
        self.assertEqual(0.0, score_before)

        state.services["nginx"].status = "running"
        score_after = grade_easy(state, state.history, metadata)
        self.assertEqual(1.0, score_after)

    def test_medium_grader_partials(self) -> None:
        state, metadata = self.generator.generate("medium")

        score_0 = grade_medium(state, state.history, metadata)
        self.assertLess(score_0, 1.0)

        state.history.append("cat /etc/nginx/nginx.conf")
        score_1 = grade_medium(state, state.history, metadata)
        self.assertEqual(0.2, score_1)

        cfg = state.filesystem["/etc/nginx/nginx.conf"]
        cfg.update_content(cfg.content.replace("INVALID", "valid"))
        state.services["nginx"].status = "running"

        score_2 = grade_medium(state, state.history, metadata)
        self.assertEqual(1.0, score_2)

    def test_hard_grader_composite(self) -> None:
        state, metadata = self.generator.generate("hard")
        score_before = grade_hard(state, state.history, metadata)
        self.assertLess(score_before, 1.0)

        state.resources.disk = 50.0
        state.resources.cpu = 20.0
        state.services["nginx"].status = "running"
        state.services["mysql"].status = "running"
        cfg = state.filesystem["/etc/nginx/nginx.conf"]
        cfg.update_content(cfg.content.replace("INVALID", "valid"))

        score_after = grade_hard(state, state.history, metadata)
        self.assertEqual(0.8, score_after)

    def test_dense_reward_penalizes_repeat_and_harmful(self) -> None:
        state, metadata = self.generator.generate("easy")
        prev = deepcopy(state)

        # Simulate critical kill transition for harmful penalty.
        state.processes = [p for p in state.processes if p.pid != 202]
        state.history = ["kill 202", "kill 202"]

        reward = compute_dense_reward(
            previous_state=prev,
            current_state=state,
            action=Action(command="kill", args="202"),
            terminal_output="Process 202 terminated",
            history=state.history,
            metadata=metadata,
            previous_score=0.0,
            current_score=0.0,
            is_success_step=False,
            action_history=state.history,
            step_count=2,
        )
        self.assertLess(reward, 0.0)

    def test_hard_grader_rewards_diagnosis_and_sequence(self) -> None:
        state, metadata = self.generator.generate("hard_3")

        # Weak attempt: restart immediately without diagnosis/fixes.
        state.history = ["restart nginx"]
        weak_score = grade_hard(state, state.history, metadata)

        # Stronger attempt: diagnose, resolve all causes, then restart.
        state.history = [
            "logs",
            "ps",
            "df",
            "cat /etc/nginx/nginx.conf",
            "kill 922",
            "kill 920",
            "rm /var/log/filler.log",
            "edit /etc/nginx/nginx.conf",
            "restart nginx",
        ]
        state.resources.cpu = 30.0
        state.resources.disk = 40.0
        cfg = state.filesystem["/etc/nginx/nginx.conf"]
        cfg.update_content(cfg.content.replace("INVALID", "valid"))
        state.services["nginx"].status = "running"

        strong_score = grade_hard(state, state.history, metadata)
        self.assertLess(weak_score, strong_score)
        self.assertGreaterEqual(strong_score, 0.8)


if __name__ == "__main__":
    unittest.main()
