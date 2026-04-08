"""Pydantic data models for the OS troubleshooting RL environment."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Action(BaseModel):
    """Represents an agent action in the environment."""

    command: str
    args: Optional[str] = None


class Observation(BaseModel):
    """Represents the limited observation available to the agent."""

    terminal_output: str
    last_command: str
    step_count: int


class Reward(BaseModel):
    """Represents scalar reward."""

    value: float
