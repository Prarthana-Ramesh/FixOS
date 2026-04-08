"""Deterministic task generator for simulated OS troubleshooting scenarios."""

from __future__ import annotations

from typing import Dict, List, Tuple

from os_simulator.failure_injection import (
    inject_config_error,
    inject_dependency_failure,
    inject_disk_full,
    inject_high_cpu_process,
    inject_log_hint,
    inject_port_conflict,
    inject_service_failure,
)
from os_simulator.main import SystemState, _recalculate_resources, build_default_state


class TaskGenerator:
    """Build deterministic troubleshooting tasks with initial system states."""

    def __init__(self) -> None:
        self._builders = {
            "easy": self._build_easy_1,
            "easy_1": self._build_easy_1,
            "easy_2": self._build_easy_2,
            "medium": self._build_medium_1,
            "medium_1": self._build_medium_1,
            "medium_2": self._build_medium_2,
            "hard": self._build_hard_1,
            "hard_1": self._build_hard_1,
            "hard_2": self._build_hard_2,
            "hard_3": self._build_hard_3,
        }

    def generate(self, task_type: str) -> Tuple[SystemState, Dict[str, object]]:
        """Generate a task state and metadata for the requested difficulty."""
        key = (task_type or "").strip().lower()
        builder = self._builders.get(key)
        if builder is None:
            supported = ", ".join(sorted(self._builders.keys()))
            raise ValueError(f"Unsupported task_type '{task_type}'. Supported: {supported}")
        return builder()

    def _build_healthy_base(self) -> SystemState:
        state = build_default_state()

        nginx = state.services.get("nginx")
        if nginx is not None:
            nginx.status = "running"
            nginx_cfg = state.filesystem.get(nginx.config_path)
            if nginx_cfg is not None:
                nginx_cfg.update_content(
                    nginx_cfg.content.replace("INVALID", "valid").replace("invalid", "valid").replace("syntax_error", "ok")
                )

        mysql = state.services.get("mysql")
        if mysql is not None:
            mysql.status = "running"

        state.logs = []
        state.history = []
        state.step_count = 0
        _recalculate_resources(state)
        return state

    def _build_easy_1(self) -> Tuple[SystemState, Dict[str, object]]:
        state = self._build_healthy_base()
        inject_service_failure(state, "nginx")

        metadata: Dict[str, object] = {
            "task_id": "easy_1",
            "description": "Nginx is down and needs a simple service restart.",
            "difficulty": "easy",
            "optimal_steps": 2,
            "expected_fixes": [
                "Check nginx status",
                "Restart nginx",
            ],
            "success_conditions": {
                "services": {"nginx": "running"},
                "resources": {"disk_below": 95.0},
            },
        }
        return state, metadata

    def _build_easy_2(self) -> Tuple[SystemState, Dict[str, object]]:
        state = self._build_healthy_base()
        inject_service_failure(state, "mysql")
        inject_log_hint(state, "ERROR", "mysql service exited with code 1")

        metadata: Dict[str, object] = {
            "task_id": "easy_2",
            "description": "MySQL is stopped and needs a direct restart.",
            "difficulty": "easy",
            "optimal_steps": 2,
            "expected_fixes": [
                "Check mysql status",
                "Restart mysql",
            ],
            "success_conditions": {
                "services": {"mysql": "running"},
                "resources": {"disk_below": 95.0},
            },
        }
        return state, metadata

    def _build_medium_1(self) -> Tuple[SystemState, Dict[str, object]]:
        state = self._build_healthy_base()
        inject_config_error(state, "nginx")
        inject_log_hint(state, "ERROR", "nginx failed: invalid config syntax")

        metadata: Dict[str, object] = {
            "task_id": "medium_1",
            "description": "Nginx fails because its config is invalid. Fix config and restart.",
            "difficulty": "medium",
            "optimal_steps": 3,
            "expected_fixes": [
                "Inspect nginx logs/config",
                "Edit nginx config to remove invalid directives",
                "Restart nginx",
            ],
            "success_conditions": {
                "services": {"nginx": "running"},
                "config_valid": {"/etc/nginx/nginx.conf": True},
                "must_check_logs": True,
            },
        }
        return state, metadata

    def _build_medium_2(self) -> Tuple[SystemState, Dict[str, object]]:
        state = self._build_healthy_base()
        inject_config_error(state, "mysql")
        inject_log_hint(state, "ERROR", "mysql failed: invalid config syntax")

        metadata: Dict[str, object] = {
            "task_id": "medium_2",
            "description": "MySQL fails due to config syntax error. Inspect logs, fix config, then restart.",
            "difficulty": "medium",
            "optimal_steps": 4,
            "expected_fixes": [
                "Inspect mysql logs/config",
                "Edit mysql config",
                "Restart mysql",
            ],
            "success_conditions": {
                "services": {"mysql": "running"},
                "config_valid": {"/etc/mysql/my.cnf": True},
                "must_check_logs": True,
            },
        }
        return state, metadata

    def _build_hard_1(self) -> Tuple[SystemState, Dict[str, object]]:
        state = self._build_healthy_base()
        inject_config_error(state, "nginx")
        inject_disk_full(state, target_percent=97.0)
        inject_high_cpu_process(state, pid=909, name="crypto_miner", cpu_usage=78.0, memory_usage=15.0)
        inject_dependency_failure(state, service_name="nginx", dependency_name="mysql")
        inject_log_hint(state, "ERROR", "nginx failed: invalid config syntax")
        inject_log_hint(state, "WARN", "disk usage above 95%")

        metadata: Dict[str, object] = {
            "task_id": "hard_1",
            "description": (
                "System has critical disk pressure, a CPU hog process, and failed services. "
                "Resolve all issues to restore healthy operation."
            ),
            "difficulty": "hard",
            "optimal_steps": 7,
            "expected_fixes": [
                "Identify and kill the high CPU process",
                "Free disk space by removing unnecessary files",
                "Restore mysql dependency",
                "Fix nginx config",
                "Restart nginx",
            ],
            "success_conditions": {
                "services": {"mysql": "running", "nginx": "running"},
                "resources": {"disk_below": 95.0, "cpu_below": 80.0},
                "config_valid": {"/etc/nginx/nginx.conf": True},
                "process_absent": [909],
            },
        }
        return state, metadata

    def _build_hard_2(self) -> Tuple[SystemState, Dict[str, object]]:
        state = self._build_healthy_base()
        inject_config_error(state, "mysql")
        inject_disk_full(state, target_percent=98.0)
        inject_high_cpu_process(state, pid=910, name="backup_job", cpu_usage=70.0, memory_usage=14.0)
        inject_dependency_failure(state, service_name="nginx", dependency_name="mysql")
        inject_log_hint(state, "ERROR", "mysql failed: invalid config syntax")
        inject_log_hint(state, "ERROR", "address already in use")

        metadata: Dict[str, object] = {
            "task_id": "hard_2",
            "description": (
                "MySQL config failure cascades to nginx dependency failure under severe disk and CPU pressure."
            ),
            "difficulty": "hard",
            "optimal_steps": 7,
            "expected_fixes": [
                "Kill high CPU process",
                "Free disk space",
                "Fix mysql config and restart mysql",
                "Restart nginx",
            ],
            "success_conditions": {
                "services": {"mysql": "running", "nginx": "running"},
                "resources": {"disk_below": 95.0, "cpu_below": 80.0},
                "config_valid": {"/etc/mysql/my.cnf": True},
                "process_absent": [910],
            },
        }
        return state, metadata

    def _build_hard_3(self) -> Tuple[SystemState, Dict[str, object]]:
        state = self._build_healthy_base()
        inject_config_error(state, "nginx")
        inject_disk_full(state, target_percent=99.0)
        # Two CPU-heavy processes: killing either one can normalize CPU.
        inject_high_cpu_process(state, pid=920, name="analytics_job", cpu_usage=48.0, memory_usage=8.0)
        inject_high_cpu_process(state, pid=921, name="batch_worker", cpu_usage=47.0, memory_usage=8.0)
        inject_port_conflict(state, pid=922, process_name="backup_listener", cpu_usage=5.0, memory_usage=3.0)
        inject_log_hint(state, "ERROR", "nginx failed: invalid config syntax")
        inject_log_hint(state, "ERROR", "address already in use")
        inject_log_hint(state, "WARN", "disk usage above 95%")

        metadata: Dict[str, object] = {
            "task_id": "hard_3",
            "description": (
                "Nginx restart is blocked by multiple causes: invalid config, port conflict, and extreme disk pressure "
                "while CPU is saturated by competing jobs."
            ),
            "difficulty": "hard",
            "optimal_steps": 8,
            "expected_fixes": [
                "Inspect logs and process list",
                "Free disk space (one of multiple removable files)",
                "Kill one heavy process and port blocker",
                "Fix nginx config",
                "Restart nginx",
            ],
            "success_conditions": {
                "services": {"nginx": "running"},
                "resources": {"disk_below": 95.0, "cpu_below": 80.0},
                "config_valid": {"/etc/nginx/nginx.conf": True},
                "process_absent": [922],
            },
        }
        return state, metadata


def _example_usage() -> None:
    generator = TaskGenerator()
    for task_type in ("easy_1", "easy_2", "medium_1", "medium_2", "hard_1", "hard_2", "hard_3"):
        state, meta = generator.generate(task_type)
        print(f"[{task_type.upper()}] {meta['task_id']}")
        print(meta["description"])
        print(f"services={ {k: v.status for k, v in state.services.items()} }")
        print(
            f"resources=cpu:{state.resources.cpu:.1f}% mem:{state.resources.memory:.1f}% disk:{state.resources.disk:.1f}%"
        )
        print(f"logs={len(state.logs)} entries")
        print("-")


if __name__ == "__main__":
    _example_usage()
