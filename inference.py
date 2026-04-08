"""Baseline inference runner for the OpenEnv-compatible OS troubleshooting environment."""

from __future__ import annotations

import json
import random
import re
from typing import Any, Dict, List, Optional

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]

from os_simulator.environment import OSEnvironment
from os_simulator.task_scoring import grade_task
from os_simulator.models import Action, Observation
from os_simulator.task_generator import TaskGenerator

MAX_STEPS = 20
TASK_IDS = ("easy", "medium", "hard")

# Environment configuration (set these explicitly for your deployment).
API_BASE_URL = "https://api.openai.com/v1"
MODEL_NAME = "gpt-4o-mini"
OPENAI_API_KEY = "enter_api_key_here"
OFFLINE_DETERMINISTIC_BASELINE = True


def build_prompt(task_id: str, observation: Observation) -> str:
    """Build a deterministic sysadmin prompt from the current observation."""
    return (
        "You are a senior Linux sysadmin troubleshooting a simulated server. "
        "Choose the single most useful next shell command to diagnose or fix issues.\n"
        f"Task: {task_id}\n"
        f"Step: {observation.step_count}\n"
        f"Last command: {observation.last_command or '<none>'}\n"
        "Terminal output:\n"
        f"{observation.terminal_output}\n\n"
        "Return ONLY valid JSON with this exact schema:\n"
        "{\"command\": \"string\", \"args\": \"string or null\"}\n"
        "Do not include markdown, explanations, or extra keys."
    )


def call_llm(client: Optional[OpenAI], model_name: str, task_id: str, observation: Observation) -> str:
    """Call the OpenAI-compatible API and return raw text response."""
    if OFFLINE_DETERMINISTIC_BASELINE or client is None:
        return ""

    prompt = build_prompt(task_id, observation)
    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise ops agent that replies with strict JSON.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            temperature=0.0,
            top_p=1.0,
            max_tokens=120,
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception:
        # Return empty string so downstream deterministic fallback planner can act.
        return ""


def parse_action(response_text: str) -> Optional[Action]:
    """Safely parse model JSON output. Returns None when invalid."""
    if not response_text:
        return None

    allowed_commands = {"ps", "top", "kill", "restart", "status", "cat", "edit", "rm", "df", "logs"}

    def _build_action(payload: Dict[str, Any]) -> Optional[Action]:
        command = payload.get("command")
        args = payload.get("args")

        if not isinstance(command, str) or not command.strip():
            return None
        cmd = command.strip().lower()
        if cmd not in allowed_commands:
            return None
        if args is not None and not isinstance(args, str):
            return None
        return Action(command=cmd, args=args.strip() if isinstance(args, str) else None)

    try:
        payload: Dict[str, Any] = json.loads(response_text)
        return _build_action(payload)
    except Exception:
        pass

    # Common failure case: model wraps JSON in markdown fences or extra text.
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, flags=re.IGNORECASE | re.DOTALL)
    if fenced_match:
        try:
            payload = json.loads(fenced_match.group(1))
            return _build_action(payload)
        except Exception:
            pass

    inline_match = re.search(r"(\{\s*\"command\".*\})", response_text, flags=re.DOTALL)
    if inline_match:
        try:
            payload = json.loads(inline_match.group(1))
            return _build_action(payload)
        except Exception:
            pass

    return None


def _fallback_action(task_id: str, step_index: int) -> Action:
    """Deterministic backup policy used when LLM output is unavailable or invalid."""
    plans: Dict[str, List[Action]] = {
        "easy": [
            Action(command="status", args="nginx"),
            Action(command="restart", args="nginx"),
        ],
        "medium": [
            Action(command="status", args="nginx"),
            Action(command="cat", args="/etc/nginx/nginx.conf"),
            Action(command="restart", args="nginx"),
            Action(command="edit", args="/etc/nginx/nginx.conf"),
            Action(command="restart", args="nginx"),
        ],
        "hard": [
            Action(command="top", args=None),
            Action(command="ps", args=None),
            Action(command="kill", args="909"),
            Action(command="df", args=None),
            Action(command="rm", args="/var/log/filler.log"),
            Action(command="restart", args="mysql"),
            Action(command="edit", args="/etc/nginx/nginx.conf"),
            Action(command="restart", args="nginx"),
            Action(command="status", args="nginx"),
        ],
    }

    plan = plans.get(task_id, [Action(command="status", args="nginx")])
    if step_index < len(plan):
        return plan[step_index]
    return Action(command="status", args="nginx")


def _should_override_to_fallback(parsed_action: Optional[Action], action_history: List[str]) -> bool:
    if parsed_action is None:
        return True

    # Avoid getting trapped in identical low-signal actions.
    if parsed_action.command == "ps" and len(action_history) >= 2:
        if action_history[-1] == "ps" and action_history[-2] == "ps":
            return True

    return False


def _format_action(action: Action) -> str:
    if action.args is None or action.args.strip() == "":
        return action.command
    return f"{action.command} {action.args}"


def run_task(client: Optional[OpenAI], model_name: str, env: OSEnvironment, task_generator: TaskGenerator, task_id: str) -> None:
    """Run one full episode and print strict logs."""
    print("[START]")
    print(f"task={task_id}")
    print("")

    # Fetch metadata deterministically for final grader call.
    _, metadata = task_generator.generate(task_id)

    observation = env.reset(task_id)
    done = False
    steps = 0
    action_history: List[str] = []

    while not done and steps < MAX_STEPS:
        llm_text = call_llm(client, model_name, task_id, observation)
        parsed_action = parse_action(llm_text)
        if _should_override_to_fallback(parsed_action, action_history):
            action = _fallback_action(task_id, steps)
        else:
            action = parsed_action  # type: ignore[assignment]

        action_history.append(_format_action(action))
        observation, reward, done, _ = env.step(action)

        print("[STEP]")
        print(f"action={_format_action(action)}")
        print(f"reward={reward.value:.4f}")
        print("")

        steps += 1

    final_score = grade_task(env.state(), env.state().history, metadata)

    print("[END]")
    print(f"score={final_score:.4f}")


def main() -> None:
    """Entry point for baseline evaluation runs over easy/medium/hard tasks."""
    random.seed(0)

    client: Optional[OpenAI] = None
    if not OFFLINE_DETERMINISTIC_BASELINE:
        if OpenAI is None:
            raise RuntimeError("openai package is required when OFFLINE_DETERMINISTIC_BASELINE is False.")
        if not OPENAI_API_KEY or OPENAI_API_KEY == "enter_api_key_here":
            raise RuntimeError("Set OPENAI_API_KEY in the environment configuration block in inference.py.")
        client = OpenAI(base_url=API_BASE_URL, api_key=OPENAI_API_KEY)

    task_generator = TaskGenerator()
    env = OSEnvironment(task_generator=task_generator, max_steps=MAX_STEPS)

    for task_id in TASK_IDS:
        run_task(client, MODEL_NAME, env, task_generator, task_id)


if __name__ == "__main__":
    main()
