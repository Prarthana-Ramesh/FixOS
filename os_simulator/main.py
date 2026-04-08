"""Deterministic simulated operating system for troubleshooting tasks.

This module models a small shell-like system with processes, services, files,
logs, and resource usage. It is intended for debugging scenarios, not as a real
OS or Linux implementation.
"""

from __future__ import annotations
import tkinter as tk
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional

class Process:
    """Process model with burst, priority, memory, and disk."""

    def __init__(self, pid, burst, priority, memory, disk):
        self.pid = pid
        self.remaining = burst
        self.priority = priority
        self.memory = memory
        self.disk = disk
        self.state = "READY"


class Kernel:
    """Kernel with round-robin scheduler (friends' original implementation)."""

    def __init__(self, time_quantum=2):
        self.queues = {}
        self.pid_counter = 1
        self.time_quantum = time_quantum
        self.gantt = []
        self.cpu = "IDLE"
        self.mem_used = 0
        self.disk_used = 0
        self.processes = []

    def create_process(self, burst, priority, memory, disk):
        p = Process(self.pid_counter, burst, priority, memory, disk)

        if self.mem_used + memory > 100 or self.disk_used + disk > 100:
            return "Not enough resources"

        self.mem_used += memory
        self.disk_used += disk

        if priority not in self.queues:
            self.queues[priority] = deque()

        self.queues[priority].append(p)
        self.processes.append(p)

        self.pid_counter += 1
        return f"Process {p.pid} created"

    def scheduler(self):
        log = ""

        while any(self.queues.values()):
            active = sorted([p for p in self.queues if self.queues[p]])
            if not active:
                break

            highest = active[0]
            queue = self.queues[highest]

            current = queue.popleft()
            current.state = "RUNNING"
            self.cpu = "BUSY"

            exec_time = min(self.time_quantum, current.remaining)
            current.remaining -= exec_time

            self.gantt.append("P" + str(current.pid))

            if current.remaining > 0:
                current.state = "WAITING"
                queue.append(current)
                log += f"Process {current.pid} paused\n"
            else:
                current.state = "TERMINATED"
                self.mem_used -= current.memory
                self.disk_used -= current.disk
                log += f"Process {current.pid} completed\n"

            self.cpu = "IDLE"

        return log


# -------- MODERN SIMULATOR --------


DISK_CAPACITY_UNITS = 500.0


# -----------------------------
# Models
# -----------------------------
@dataclass
class Process_sim:
    """Represents a simulated process."""

    pid: int
    name: str
    cpu_usage: float
    memory_usage: float
    status: str  # running, sleeping, zombie
    priority: int


@dataclass
class Service:
    """Represents a simulated service."""

    name: str
    status: str  # running, stopped, failed
    config_path: str
    dependencies: List[str]


@dataclass
class File:
    """Represents a file in the simulated filesystem."""

    path: str
    content: str
    size: int = field(init=False)

    def __post_init__(self) -> None:
        self.size = len(self.content)

    def update_content(self, new_content: str) -> None:
        self.content = new_content
        self.size = len(new_content)


@dataclass
class ResourceUsage:
    """Represents global resource usage percentages."""

    cpu: float
    memory: float
    disk: float


# -----------------------------
# State
# -----------------------------
@dataclass
class SystemState:
    """Holds all mutable simulator state."""

    processes: List[Process_sim]
    services: Dict[str, Service]
    filesystem: Dict[str, File]
    logs: List[str]
    resources: ResourceUsage
    history: List[str]
    step_count: int


def _append_log(state: SystemState, level: str, message: str) -> None:
    state.logs.append(f"[{level}] {message}")


def _used_disk_units(state: SystemState) -> float:
    return float(sum(file.size for file in state.filesystem.values()))


def _has_enough_disk_for_delta(state: SystemState, delta_units: int) -> bool:
    if delta_units <= 0:
        return True
    return (_used_disk_units(state) + delta_units) <= DISK_CAPACITY_UNITS


def _recalculate_resources(state: SystemState) -> None:
    total_cpu = sum(p.cpu_usage for p in state.processes if p.status == "running")
    total_mem = sum(p.memory_usage for p in state.processes)
    total_disk_units = _used_disk_units(state)

    state.resources.cpu = min(total_cpu, 100.0)
    state.resources.memory = min(total_mem, 100.0)
    state.resources.disk = min((total_disk_units / DISK_CAPACITY_UNITS) * 100.0, 100.0)

    if state.resources.disk > 95.0:
        _append_log(state, "WARN", "disk usage above 95%")


def _is_config_valid(content: str) -> bool:
    """Very small deterministic config validator used by restart."""
    bad_markers = ("INVALID", "invalid", "syntax_error", "ERROR")
    return not any(marker in content for marker in bad_markers)


# -----------------------------
# Command execution
# -----------------------------
def execute_command(state: SystemState, command: str, args: Optional[str] = None) -> str:
    """Execute one shell-like command and mutate state deterministically."""
    cmd = (command or "").strip().lower()
    arg = (args or "").strip()

    raw = cmd if not arg else f"{cmd} {arg}"
    state.history.append(raw)
    state.step_count += 1

    if cmd == "ps":
        if not state.processes:
            return "PID   NAME           CPU%   MEM%   STATUS    PRI\n(no processes)"
        lines = ["PID   NAME           CPU%   MEM%   STATUS    PRI"]
        for p in sorted(state.processes, key=lambda proc: proc.pid):
            lines.append(
                f"{p.pid:<5} {p.name:<14} {p.cpu_usage:>4.1f}   {p.memory_usage:>4.1f}   {p.status:<8} {p.priority}"
            )
        return "\n".join(lines)

    if cmd == "top":
        _recalculate_resources(state)
        return (
            "top - simulated system\n"
            f"CPU: {state.resources.cpu:.1f}%\n"
            f"MEM: {state.resources.memory:.1f}%\n"
            f"DISK: {state.resources.disk:.1f}%"
        )

    if cmd == "kill":
        if not arg:
            return "kill: missing pid"
        if not arg.isdigit():
            return f"kill: invalid pid '{arg}'"
        pid = int(arg)
        target = next((p for p in state.processes if p.pid == pid), None)
        if target is None:
            return f"kill: ({pid}) - no such process"

        state.processes = [p for p in state.processes if p.pid != pid]
        _recalculate_resources(state)
        _append_log(state, "INFO", f"process {pid} killed")
        return f"Process {pid} terminated"

    if cmd == "restart":
        if not arg:
            return "restart: missing service name"
        service = state.services.get(arg)
        if service is None:
            return f"restart: service '{arg}' not found"

        _recalculate_resources(state)
        if state.resources.disk > 95.0:
            service.status = "failed"
            _append_log(state, "ERROR", f"{service.name} failed due to insufficient disk space")
            return f"Failed to restart {service.name}: disk usage too high"

        missing_dep = next(
            (dep for dep in service.dependencies if state.services.get(dep, Service(dep, "stopped", "", [])).status != "running"),
            None,
        )
        if missing_dep is not None:
            service.status = "failed"
            _append_log(state, "ERROR", f"{service.name} failed because dependency {missing_dep} is not running")
            return f"Failed to restart {service.name}: dependency {missing_dep} is not running"

        # Simulate shared port contention from rogue listeners.
        port_blocker = next(
            (
                p for p in state.processes
                if p.status == "running" and p.name in {"port_blocker", "nginx_stale", "backup_listener"}
            ),
            None,
        )
        if port_blocker is not None:
            service.status = "failed"
            _append_log(state, "ERROR", "address already in use")
            return f"Failed to restart {service.name}: address already in use"

        config = state.filesystem.get(service.config_path)
        if config is None:
            service.status = "failed"
            _append_log(state, "ERROR", f"{service.name} failed due to missing config")
            return f"Failed to restart {service.name}: missing config"

        if _is_config_valid(config.content):
            service.status = "running"
            _append_log(state, "INFO", f"{service.name} restarted successfully")
            return f"{service.name} restarted"

        service.status = "failed"
        _append_log(state, "ERROR", f"{service.name} failed due to invalid config")
        return f"{service.name} restart failed: invalid config"

    if cmd == "status":
        if not arg:
            return "status: missing service name"
        service = state.services.get(arg)
        if service is None:
            return f"status: service '{arg}' not found"
        return f"{service.name} is {service.status}"

    if cmd == "cat":
        if not arg:
            return "cat: missing file path"
        file_obj = state.filesystem.get(arg)
        if file_obj is None:
            return f"cat: {arg}: No such file"
        return file_obj.content

    if cmd == "edit":
        if not arg:
            return "edit: missing file path"
        file_obj = state.filesystem.get(arg)
        if file_obj is None:
            return f"edit: {arg}: No such file"

        if "INVALID" in file_obj.content or "invalid" in file_obj.content:
            new_content = (
                file_obj.content.replace("INVALID", "valid")
                .replace("invalid", "valid")
                .replace("syntax_error", "ok")
            )
        else:
            new_content = file_obj.content + "\n# edited"

        delta_units = len(new_content) - len(file_obj.content)
        if not _has_enough_disk_for_delta(state, delta_units):
            _append_log(state, "ERROR", f"edit failed for {arg}: no space left on device")
            return f"edit: {arg}: No space left on device"

        file_obj.update_content(new_content)
        _recalculate_resources(state)
        _append_log(state, "INFO", f"file {arg} edited")
        return f"Edited {arg}"

    if cmd == "rm":
        if not arg:
            return "rm: missing file path"
        file_obj = state.filesystem.get(arg)
        if file_obj is None:
            return f"rm: cannot remove '{arg}': No such file"

        del state.filesystem[arg]
        _recalculate_resources(state)
        _append_log(state, "INFO", f"file {arg} removed")
        return f"Removed {arg}"

    if cmd == "df":
        _recalculate_resources(state)
        return (
            "Filesystem      Size  Used Avail Use% Mounted on\n"
            f"simfs           100   {state.resources.disk:>4.1f} {100.0 - state.resources.disk:>5.1f} {state.resources.disk:>4.1f}% /"
        )

    if cmd == "logs":
        if not state.logs:
            return "(no logs)"
        return "\n".join(state.logs)

    return f"{cmd}: command not found"


# -----------------------------
# Simulator
# -----------------------------
class Simulator:
    """Facade for interacting with the simulated system."""

    def __init__(self, initial_state: Optional[SystemState] = None) -> None:
        self._state = initial_state or build_default_state()

    def execute(self, command: str, args: Optional[str] = None) -> str:
        """Execute a command; supports either split args or a full shell line."""
        if args is None:
            tokens = command.strip().split(maxsplit=1)
            if not tokens:
                return ""
            cmd = tokens[0]
            arg = tokens[1] if len(tokens) > 1 else None
            return execute_command(self._state, cmd, arg)
        return execute_command(self._state, command, args)

    def get_state(self) -> SystemState:
        """Return full simulator state object."""
        return self._state

    def reset(self, initial_state: Optional[SystemState] = None) -> None:
        """Reset simulator to provided state or default state."""
        self._state = initial_state or build_default_state()


def build_default_state() -> SystemState:
    """Create a deterministic starting system state."""
    processes = [
        Process_sim(pid=101, name="nginx", cpu_usage=8.0, memory_usage=6.0, status="running", priority=10),
        Process_sim(pid=202, name="mysql", cpu_usage=16.0, memory_usage=18.0, status="running", priority=5),
        Process_sim(pid=303, name="worker", cpu_usage=4.0, memory_usage=3.0, status="sleeping", priority=15),
    ]

    filesystem = {
        "/etc/nginx/nginx.conf": File(
            path="/etc/nginx/nginx.conf",
            content="worker_processes 1;\nINVALID directive_here;\n",
        ),
        "/etc/mysql/my.cnf": File(
            path="/etc/mysql/my.cnf",
            content="[mysqld]\nmax_connections=150\n",
        ),
        "/var/log/nginx/error.log": File(
            path="/var/log/nginx/error.log",
            content="[ERROR] nginx failed due to invalid config\n",
        ),
    }

    services = {
        "mysql": Service(name="mysql", status="running", config_path="/etc/mysql/my.cnf", dependencies=[]),
        "nginx": Service(name="nginx", status="failed", config_path="/etc/nginx/nginx.conf", dependencies=["mysql"]),
    }

    state = SystemState(
        processes=processes,
        services=services,
        filesystem=filesystem,
        logs=["[ERROR] nginx failed due to invalid config"],
        resources=ResourceUsage(cpu=0.0, memory=0.0, disk=0.0),
        history=[],
        step_count=0,
    )
    _recalculate_resources(state)
    return state


def _run_shell() -> None:
    """Minimal interactive loop for manual testing."""
    # Example commands to test functionality in order:
    # ps
    # top
    # status nginx
    # cat /etc/nginx/nginx.conf
    # restart nginx
    # edit /etc/nginx/nginx.conf
    # restart nginx
    # status nginx
    # kill 202
    # ps
    # df
    # rm /var/log/nginx/error.log
    # df
    # logs
    simulator = Simulator()
    print("SimOS shell. Type 'exit' to quit.")
    while True:
        raw = input("$ ").strip()
        if raw in {"exit", "quit"}:
            break
        if not raw:
            continue
        print(simulator.execute(raw))


if __name__ == "__main__":
    _run_shell()