import unittest

from os_simulator.environment import OSEnvironment
from os_simulator.models import Action
from os_simulator.task_generator import TaskGenerator


class OSEnvironmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = OSEnvironment(task_generator=TaskGenerator(), max_steps=20)

    def test_reset_returns_limited_observation(self) -> None:
        obs = self.env.reset("easy")

        self.assertEqual(0, obs.step_count)
        self.assertEqual("", obs.last_command)
        self.assertIn("Task loaded", obs.terminal_output)

    def test_medium_flow_reaches_success(self) -> None:
        self.env.reset("medium")

        steps = [
            Action(command="cat", args="/etc/nginx/nginx.conf"),
            Action(command="edit", args="/etc/nginx/nginx.conf"),
            Action(command="restart", args="nginx"),
        ]

        done = False
        info = {}
        for action in steps:
            _, _, done, info = self.env.step(action)

        self.assertTrue(done)
        self.assertTrue(info["success"])
        self.assertEqual(1.0, info["score"])

        with self.assertRaises(RuntimeError):
            self.env.step(Action(command="ps"))

    def test_determinism_same_actions_same_result(self) -> None:
        actions = [
            Action(command="status", args="nginx"),
            Action(command="cat", args="/etc/nginx/nginx.conf"),
            Action(command="edit", args="/etc/nginx/nginx.conf"),
            Action(command="restart", args="nginx"),
        ]

        env_a = OSEnvironment(task_generator=TaskGenerator(), max_steps=20)
        env_b = OSEnvironment(task_generator=TaskGenerator(), max_steps=20)

        env_a.reset("medium")
        env_b.reset("medium")

        history_a = []
        history_b = []

        for action in actions:
            obs_a, rew_a, done_a, info_a = env_a.step(action)
            obs_b, rew_b, done_b, info_b = env_b.step(action)
            history_a.append((obs_a.terminal_output, rew_a.value, done_a, info_a["score"]))
            history_b.append((obs_b.terminal_output, rew_b.value, done_b, info_b["score"]))

        self.assertEqual(history_a, history_b)

    def test_done_on_max_steps(self) -> None:
        env = OSEnvironment(task_generator=TaskGenerator(), max_steps=2)
        env.reset("easy")

        _, _, done_1, _ = env.step(Action(command="ps"))
        _, _, done_2, info_2 = env.step(Action(command="ps"))

        self.assertFalse(done_1)
        self.assertTrue(done_2)
        self.assertTrue(info_2["max_steps_reached"])

    def test_easy_early_termination_after_success(self) -> None:
        env = OSEnvironment(task_generator=TaskGenerator(), max_steps=20)
        env.reset("easy_1")

        _, _, done, info = env.step(Action(command="restart", args="nginx"))
        self.assertTrue(done)
        self.assertTrue(info["success"])

        with self.assertRaises(RuntimeError):
            env.step(Action(command="status", args="nginx"))


if __name__ == "__main__":
    unittest.main()
