"""Failure injection utilities for deterministic troubleshooting scenarios."""

from __future__ import annotations

from os_simulator.main import (
    File,
    Process_sim,
    SystemState,
    _append_log,
    _recalculate_resources,
)


def inject_service_failure(state: SystemState, service_name: str = "nginx") -> None:
    """Mark a service as stopped to create an easy restart task."""
    service = state.services.get(service_name)
    if service is None:
        return
    service.status = "stopped"
    _append_log(state, "ERROR", f"{service_name} service stopped unexpectedly")
    _recalculate_resources(state)


def inject_config_error(state: SystemState, service_name: str = "nginx") -> None:
    """Inject an invalid service config that blocks restart."""
    service = state.services.get(service_name)
    if service is None:
        return

    config = state.filesystem.get(service.config_path)
    if config is None:
        config = File(path=service.config_path, content="")
        state.filesystem[service.config_path] = config

    if "INVALID" not in config.content:
        content = config.content.rstrip("\n")
        config.update_content(content + "\nINVALID broken_directive;\n")

    service.status = "failed"
    _append_log(state, "ERROR", f"{service_name} failed: invalid config syntax")
    _recalculate_resources(state)


def inject_disk_full(state: SystemState, target_percent: float = 97.0) -> None:
    """Fill disk to a target percentage by creating a deterministic filler file."""
    _recalculate_resources(state)
    if state.resources.disk >= target_percent:
        _append_log(state, "WARN", "disk usage above 95%")
        return

    total_units = 500
    target_units = int((target_percent / 100.0) * total_units)
    current_units = sum(file.size for file in state.filesystem.values())
    filler_needed = max(target_units - current_units, 0)

    # Split pressure across two files so multiple cleanup actions can work.
    half = filler_needed // 2
    state.filesystem["/var/log/filler.log"] = File(path="/var/log/filler.log", content="X" * half)
    state.filesystem["/tmp/cache.tmp"] = File(path="/tmp/cache.tmp", content="Y" * (filler_needed - half))
    _recalculate_resources(state)
    _append_log(state, "WARN", "disk usage above 95%")
    _append_log(state, "ERROR", "write failed: no space left on device")


def inject_high_cpu_process(
    state: SystemState,
    pid: int = 909,
    name: str = "cpu_hog",
    cpu_usage: float = 72.0,
    memory_usage: float = 12.0,
) -> None:
    """Add a heavy process to simulate CPU pressure."""
    if any(proc.pid == pid for proc in state.processes):
        return

    state.processes.append(
        Process_sim(
            pid=pid,
            name=name,
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            status="running",
            priority=1,
        )
    )
    _recalculate_resources(state)
    _append_log(state, "WARN", f"high CPU usage caused by process {pid} ({name})")
    _append_log(state, "ERROR", "address already in use")


def inject_port_conflict(
    state: SystemState,
    pid: int = 950,
    process_name: str = "port_blocker",
    cpu_usage: float = 8.0,
    memory_usage: float = 4.0,
) -> None:
    """Create deterministic port conflict by adding a listener-like process."""
    if any(proc.pid == pid for proc in state.processes):
        return

    state.processes.append(
        Process_sim(
            pid=pid,
            name=process_name,
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            status="running",
            priority=2,
        )
    )
    _recalculate_resources(state)
    _append_log(state, "ERROR", "address already in use")


def inject_dependency_failure(
    state: SystemState,
    service_name: str = "nginx",
    dependency_name: str = "mysql",
) -> None:
    """Break a dependency chain by stopping a dependency service."""
    dependency = state.services.get(dependency_name)
    target = state.services.get(service_name)
    if dependency is None or target is None:
        return

    dependency.status = "stopped"
    target.status = "failed"
    _append_log(state, "ERROR", f"{service_name} failed because dependency {dependency_name} is not running")
    _recalculate_resources(state)


def inject_log_hint(state: SystemState, level: str, message: str) -> None:
    """Append deterministic troubleshooting hint log entries."""
    _append_log(state, level, message)
