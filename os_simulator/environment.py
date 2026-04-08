"""OpenEnv-style environment built on top of the deterministic OS simulator."""

from __future__ import annotations

from copy import deepcopy
from typing import Dict, Optional, Tuple

from os_simulator.task_scoring import grade_task, is_task_success
from os_simulator.main import Simulator, SystemState
from os_simulator.models import Action, Observation, Reward
from os_simulator.reward import compute_dense_reward


class OSEnvironment:
    """OpenEnv-compatible interface: reset, step, state."""

    def __init__(self, task_generator, max_steps: int = 20) -> None:
        self.task_generator = task_generator
        self.max_steps = max_steps
        self._simulator: Optional[Simulator] = None
        self._metadata: Dict[str, object] = {}
        self._last_command: str = ""
        self._last_output: str = ""
        self._done: bool = False
        self._action_history: list[str] = []

    def _normalize_task_id(self, task_id: str) -> str:
        key = (task_id or "").strip().lower()
        aliases = {
            "easy": "easy_1",
            "medium": "medium_1",
            "hard": "hard_1",
            "easy-nginx-restart-001": "easy_1",
            "medium-nginx-config-001": "medium_1",
            "hard-multi-issue-001": "hard_1",
        }
        if key in aliases:
            return aliases[key]
        if key in {"easy_1", "easy_2", "medium_1", "medium_2", "hard_1", "hard_2", "hard_3"}:
            return key
        raise ValueError(
            "Unsupported task_id '"
            f"{task_id}'"
            ". Use easy|medium|hard or variant IDs easy_1/easy_2/medium_1/medium_2/hard_1/hard_2/hard_3."
        )

    def reset(self, task_id: str) -> Observation:
        """Generate deterministic task state and return initial observation."""
        task_type = self._normalize_task_id(task_id)
        initial_state, metadata = self.task_generator.generate(task_type)

        initial_state.history = []
        initial_state.step_count = 0

        self._simulator = Simulator(initial_state=initial_state)
        self._metadata = metadata
        self._last_command = ""
        self._last_output = f"Task loaded: {metadata.get('description', '')}"
        self._done = False
        self._action_history = []

        return Observation(
            terminal_output=self._last_output,
            last_command=self._last_command,
            step_count=self._simulator.get_state().step_count,
        )

    def step(self, action: Action) -> Tuple[Observation, Reward, bool, Dict[str, object]]:
        """Execute one action and return observation, reward, done, and info."""
        if self._simulator is None:
            raise RuntimeError("Environment must be reset before step().")
        if self._done:
            raise RuntimeError("Episode has already terminated. Call reset() before taking more steps.")

        previous_state: SystemState = deepcopy(self._simulator.get_state())
        previous_score = grade_task(previous_state, previous_state.history, self._metadata)

        output = self._simulator.execute(action.command, action.args)
        current_state = self._simulator.get_state()

        command_text = (action.command or "").strip()
        arg_text = (action.args or "").strip()
        self._last_command = command_text if not arg_text else f"{command_text} {arg_text}"
        self._last_output = output
        self._action_history.append(self._last_command)

        current_score = grade_task(current_state, current_state.history, self._metadata)
        success = is_task_success(current_state, current_state.history, self._metadata)
        max_steps_reached = current_state.step_count >= self.max_steps
        done = success or max_steps_reached
        self._done = done

        reward_value = compute_dense_reward(
            previous_state=previous_state,
            current_state=current_state,
            action=action,
            terminal_output=output,
            history=current_state.history,
            metadata=self._metadata,
            previous_score=previous_score,
            current_score=current_score,
            is_success_step=success,
            action_history=self._action_history,
            step_count=current_state.step_count,
        )

        observation = Observation(
            terminal_output=output,
            last_command=self._last_command,
            step_count=current_state.step_count,
        )

        info: Dict[str, object] = {
            "task_id": self._metadata.get("task_id", "unknown"),
            "difficulty": self._metadata.get("difficulty", "unknown"),
            "score": round(current_score, 4),
            "success": success,
            "max_steps_reached": max_steps_reached,
            "action_history": list(self._action_history),
        }

        return observation, Reward(value=reward_value), done, info

    def state(self) -> SystemState:
        """Return full internal simulator state."""
        if self._simulator is None:
            raise RuntimeError("Environment has no active simulator. Call reset() first.")
        return self._simulator.get_state()


def _example_usage() -> None:
    from os_simulator.task_generator import TaskGenerator

    env = OSEnvironment(task_generator=TaskGenerator(), max_steps=20)

    obs = env.reset("medium")
    print("reset:", obs.model_dump())

    actions = [
        Action(command="status", args="nginx"),
        Action(command="cat", args="/etc/nginx/nginx.conf"),
        Action(command="edit", args="/etc/nginx/nginx.conf"),
        Action(command="restart", args="nginx"),
    ]

    for action in actions:
        obs, rew, done, info = env.step(action)
        print("step:", obs.model_dump(), "reward:", rew.value, "done:", done, "info:", info)
        if done:
            break

    final_score = info["score"]
    print("final_grade:", final_score)


if __name__ == "__main__":
    _example_usage()
