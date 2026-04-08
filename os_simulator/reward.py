"""Dense reward shaping for the OS troubleshooting RL environment."""

from __future__ import annotations

from typing import Dict, Iterable

from os_simulator.main import SystemState
from os_simulator.models import Action


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _action_text(action: Action) -> str:
    cmd = (action.command or "").strip().lower()
    arg = (action.args or "").strip()
    return cmd if not arg else f"{cmd} {arg}"


def compute_dense_reward(
    previous_state: SystemState,
    current_state: SystemState,
    action: Action,
    terminal_output: str,
    history: Iterable[str],
    metadata: Dict[str, object],
    previous_score: float,
    current_score: float,
    is_success_step: bool,
    action_history: Iterable[str],
    step_count: int,
) -> float:
    """Compute dense reward using state transition, action, and history signals."""
    optimal_steps = int(metadata.get("optimal_steps", 0) or 0)

    reward = 0.0
    cmd = (action.command or "").strip().lower()
    arg = (action.args or "").strip()
    output = (terminal_output or "").lower()

    useful_exploration = {"ps", "top", "df", "status", "logs", "cat"}
    if cmd in useful_exploration:
        reward += 0.1

    looked_at_relevant_artifact = cmd == "logs" or (cmd == "cat" and ("/var/log" in arg or "/etc/" in arg))
    issue_clues = ("error", "warn", "failed", "invalid", "dependency", "no space")
    if looked_at_relevant_artifact and any(clue in output for clue in issue_clues):
        reward += 0.2

    if cmd == "edit":
        reward += 0.3

    if cmd == "kill" and arg.isdigit():
        pid = int(arg)
        previous_proc = next((p for p in previous_state.processes if p.pid == pid), None)
        if previous_proc is not None:
            if previous_proc.cpu_usage >= 50.0:
                reward += 0.3

    if cmd == "rm" and current_state.resources.disk < previous_state.resources.disk:
        reward += 0.3

    if cmd == "restart" and arg:
        service_name = arg
        prev_service = previous_state.services.get(service_name)
        curr_service = current_state.services.get(service_name)
        if prev_service is not None and curr_service is not None:
            if prev_service.status != "running" and curr_service.status == "running":
                reward += 0.5

        # Penalize restarting before diagnosis or before attempting fixes.
        history_list = list(history)
        prior = history_list[:-1]
        diagnosed = any(h.startswith("logs") or h.startswith("cat /var/log") or h.startswith("status ") for h in prior)
        attempted_fix = any(h.startswith("edit ") or h.startswith("rm ") or h.startswith("kill ") for h in prior)
        if not diagnosed:
            reward -= 0.2
        if not attempted_fix:
            reward -= 0.2

    if previous_state.resources.disk > 95.0 and current_state.resources.disk <= 95.0:
        reward += 0.5

    if is_success_step:
        reward += 0.5

    score_delta = current_score - previous_score
    if score_delta > 0:
        reward += 0.4 * score_delta

    if optimal_steps > 0 and step_count > optimal_steps:
        reward -= 0.05 * (step_count - optimal_steps)

    if "command not found" in output or "missing" in output or "no such" in output:
        reward -= 0.1

    if cmd == "restart" and ("invalid config" in output or "address already in use" in output or "dependency" in output):
        reward -= 0.2

    history_list = list(history)
    action_history_list = list(action_history)
    if len(action_history_list) >= 2 and action_history_list[-1] == action_history_list[-2]:
        reward -= 0.3

    if len(history_list) >= 2 and history_list[-1] == history_list[-2]:
        reward -= 0.2

    state_unchanged = (
        previous_state.resources.cpu == current_state.resources.cpu
        and previous_state.resources.memory == current_state.resources.memory
        and previous_state.resources.disk == current_state.resources.disk
        and [(p.pid, p.status, p.cpu_usage, p.memory_usage) for p in previous_state.processes]
        == [(p.pid, p.status, p.cpu_usage, p.memory_usage) for p in current_state.processes]
        and {name: svc.status for name, svc in previous_state.services.items()}
        == {name: svc.status for name, svc in current_state.services.items()}
    )
    if state_unchanged and cmd in {"ps", "status", "top", "logs", "df"}:
        reward -= 0.2
    elif state_unchanged:
        reward -= 0.4

    if cmd == "kill" and arg.isdigit():
        pid = int(arg)
        killed_critical = any(
            p.pid == pid and p.name in {"mysql", "nginx"} for p in previous_state.processes
        ) and not any(p.pid == pid for p in current_state.processes)
        if killed_critical:
            reward -= 0.5

    if cmd == "rm" and arg and arg in {svc.config_path for svc in previous_state.services.values()}:
        reward -= 0.5

    if cmd == "rm" and current_state.resources.disk >= previous_state.resources.disk:
        reward -= 0.2

    if cmd == "restart" and "failed" in output and "disk usage too high" in output:
        reward -= 0.1

    _ = _action_text(action)
    return _clamp(reward, -1.0, 1.0)
