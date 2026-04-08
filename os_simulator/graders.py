"""Deterministic task graders for easy, medium, and hard troubleshooting tasks."""

from __future__ import annotations

from typing import Dict, Iterable

from os_simulator.main import SystemState, _is_config_valid

tasks = {
    "high_cpu": {
        "expected_actions": ["check_process", "reduce_load"]
    },
    "normal": {
        "expected_actions": []
    }
}


def agent_from_kernel(kernel):
    if kernel.cpu == "BUSY":
        return {
            "problem": "high_cpu",
            "actions": ["check_process"]
        }
    else:
        return {
            "problem": "normal",
            "actions": []
        }


def check_problem(agent_output):
    if agent_output["problem"] in tasks:
        return 1
    return 0


def check_actions(agent_output):
    problem = agent_output["problem"]
    expected = tasks[problem]["expected_actions"]

    if len(expected) == 0:
        return 1

    correct = 0
    for act in agent_output["actions"]:
        if act in expected:
            correct += 1

    return correct / len(expected)


def get_score(agent_output):
    p = check_problem(agent_output)
    a = check_actions(agent_output)

    return (p + a) / 2


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _checked_logs(history: Iterable[str]) -> bool:
    return any(
        entry.startswith("logs")
        or entry.startswith("cat /var/log")
        or entry.startswith("cat /etc/")
        for entry in history
    )


def _configs_valid(state: SystemState, config_rules: Dict[str, object]) -> bool:
    if not config_rules:
        return True
    for path, expected in config_rules.items():
        file_obj = state.filesystem.get(path)
        if file_obj is None:
            return False
        if bool(expected) != _is_config_valid(file_obj.content):
            return False
    return True


def _services_in_state(state: SystemState, services_rules: Dict[str, object]) -> bool:
    if not services_rules:
        return True
    return all(state.services.get(name) and state.services[name].status == status for name, status in services_rules.items())


def _repeated_actions(history: Iterable[str]) -> int:
    history_list = list(history)
    return sum(1 for i in range(1, len(history_list)) if history_list[i] == history_list[i - 1])


def _efficiency_score(history: Iterable[str], optimal_steps: int) -> float:
    history_list = list(history)
    if optimal_steps <= 0:
        return 0.0
    if len(history_list) == 0:
        return 0.0
    if len(history_list) < optimal_steps:
        return 0.0
    if len(history_list) == optimal_steps:
        return 1.0
    overshoot = len(history_list) - optimal_steps
    return _clamp01(1.0 - 0.05 * overshoot)


def _success_conditions_met(state: SystemState, conditions: Dict[str, object]) -> bool:
    services = conditions.get("services", {})
    for service_name, expected_status in services.items():
        service = state.services.get(service_name)
        if service is None or service.status != expected_status:
            return False

    resources = conditions.get("resources", {})
    if "disk_below" in resources and not (state.resources.disk < float(resources["disk_below"])):
        return False
    if "cpu_below" in resources and not (state.resources.cpu < float(resources["cpu_below"])):
        return False

    config_valid = conditions.get("config_valid", {})
    for path, expected in config_valid.items():
        file_obj = state.filesystem.get(path)
        if file_obj is None:
            return False
        if bool(expected) != _is_config_valid(file_obj.content):
            return False

    process_absent = conditions.get("process_absent", [])
    active_pids = {proc.pid for proc in state.processes}
    for pid in process_absent:
        if int(pid) in active_pids:
            return False

    return True


def grade_easy(state: SystemState, history: Iterable[str], metadata: Dict[str, object]) -> float:
    """Easy: full score when service targets are running."""
    del history
    conditions = metadata.get("success_conditions", {})
    return 1.0 if _success_conditions_met(state, conditions) else 0.0


def grade_medium(state: SystemState, history: Iterable[str], metadata: Dict[str, object]) -> float:
    """Medium: logs checked (+0.2), config fixed (+0.3), service running (+0.5)."""
    conditions = metadata.get("success_conditions", {})
    score = 0.0

    must_check_logs = bool(conditions.get("must_check_logs", False))
    logs_checked = _checked_logs(history)
    if logs_checked or not must_check_logs:
        score += 0.2

    config_valid_rules = conditions.get("config_valid", {})
    if _configs_valid(state, config_valid_rules):
        score += 0.3

    services = conditions.get("services", {})
    if _services_in_state(state, services):
        score += 0.5

    optimal_steps = int(metadata.get("optimal_steps", 0) or 0)
    if optimal_steps > 0:
        score += 0.1 * _efficiency_score(history, optimal_steps)

    repeats = _repeated_actions(history)
    score -= min(0.1, repeats * 0.03)

    return round(_clamp01(score), 6)


def grade_hard(state: SystemState, history: Iterable[str], metadata: Dict[str, object]) -> float:
    """Hard: quality-aware grading with diagnosis, root-cause handling, and penalties."""
    conditions = metadata.get("success_conditions", {})
    resources = conditions.get("resources", {})
    history_list = list(history)

    disk_target = float(resources.get("disk_below", 95.0))
    cpu_target = float(resources.get("cpu_below", 80.0))

    disk_ok = state.resources.disk < disk_target
    cpu_ok = state.resources.cpu < cpu_target

    config_valid_rules = conditions.get("config_valid", {})
    config_ok = _configs_valid(state, config_valid_rules)

    services = conditions.get("services", {})
    services_ok = _services_in_state(state, services)

    score = 0.0
    logs_checked = _checked_logs(history_list)
    if logs_checked:
        score += 0.2

    root_cause_identified = any(cmd.startswith("ps") or cmd.startswith("top") for cmd in history_list) and any(
        cmd.startswith("df") or cmd.startswith("cat /etc") for cmd in history_list
    )
    if root_cause_identified:
        score += 0.2

    if disk_ok:
        score += 0.2
    if cpu_ok:
        score += 0.1
    if config_ok:
        score += 0.2
    if services_ok:
        score += 0.3

    # Penalize poor sequencing: restart before diagnosis/fix.
    restart_idx = next((i for i, cmd in enumerate(history_list) if cmd.startswith("restart ")), None)
    if restart_idx is not None:
        prior = history_list[:restart_idx]
        diagnosed = any(c.startswith("logs") or c.startswith("cat /var/log") or c.startswith("status ") for c in prior)
        attempted_fix = any(c.startswith("edit ") or c.startswith("rm ") or c.startswith("kill ") for c in prior)
        if not diagnosed:
            score -= 0.1
        if not attempted_fix:
            score -= 0.1

    # Penalize redundant commands to differentiate weak agents.
    repeats = sum(1 for i in range(1, len(history_list)) if history_list[i] == history_list[i - 1])
    score -= min(0.2, repeats * 0.02)

    # Efficiency component: compact, correct solutions get rewarded.
    optimal_steps = int(metadata.get("optimal_steps", 0) or 0)
    if optimal_steps > 0:
        score += 0.2 * _efficiency_score(history_list, optimal_steps)

    # Penalize clearly unnecessary actions that do not affect state quality.
    excessive_steps = max(0, len(history_list) - optimal_steps) if optimal_steps > 0 else 0
    score -= min(0.1, excessive_steps * 0.01)

    return round(_clamp01(score), 6)


def grade_task(state: SystemState, history: Iterable[str], metadata: Dict[str, object]) -> float:
    """Route grading by metadata difficulty."""
    difficulty = str(metadata.get("difficulty", "easy")).lower()
    if difficulty == "easy":
        return grade_easy(state, history, metadata)
    if difficulty == "medium":
        return grade_medium(state, history, metadata)
    if difficulty == "hard":
        return grade_hard(state, history, metadata)
    return 0.0


def is_task_success(state: SystemState, history: Iterable[str], metadata: Dict[str, object]) -> bool:
    """Returns True when success conditions are fully satisfied."""
    score = grade_task(state, history, metadata)
    return score >= 1.0 and _success_conditions_met(state, metadata.get("success_conditions", {}))
