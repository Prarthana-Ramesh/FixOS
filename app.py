"""FastAPI server for the deterministic OS troubleshooting environment."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator

from os_simulator.environment import OSEnvironment
from os_simulator.models import Action
from os_simulator.task_generator import TaskGenerator

app = FastAPI(title="FixOS API", version="1.0.0")
_env = OSEnvironment(TaskGenerator())
_env.reset("easy_1")


class ResetRequest(BaseModel):
    """Request body for resetting the environment."""

    task_id: str

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("task_id must be a non-empty string")
        return value.strip()


class StepRequest(BaseModel):
    """Request body for stepping the environment."""

    command: str
    args: Optional[str] = None

    @field_validator("command")
    @classmethod
    def validate_command(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("command must be a non-empty string")
        return value.strip()

    @field_validator("args")
    @classmethod
    def normalize_args(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("args must be a string or null")
        value = value.strip()
        return value or None


def _to_jsonable(value: Any) -> Any:
    """Recursively convert values into JSON-serializable structures."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, BaseModel):
        if hasattr(value, "model_dump"):
            return {k: _to_jsonable(v) for k, v in value.model_dump().items()}
        return {k: _to_jsonable(v) for k, v in value.dict().items()}
    if is_dataclass(value):
        return {k: _to_jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump())
    if hasattr(value, "dict"):
        return _to_jsonable(value.dict())
    return str(value)


@app.get("/")
def health_check() -> Dict[str, str]:
    """Simple readiness endpoint."""
    return {"status": "running"}


@app.post("/reset")
def reset_environment(payload: ResetRequest) -> Dict[str, Any]:
    """Reset the environment to the requested deterministic task variant."""
    try:
        observation = _env.reset(payload.task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"reset failed: {exc}") from exc

    return _to_jsonable(observation)


@app.post("/step")
def step_environment(payload: StepRequest) -> Dict[str, Any]:
    """Execute one environment step and return the transition payload."""
    try:
        action = Action(command=payload.command, args=payload.args)
        observation, reward, done, info = _env.step(action)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"step failed: {exc}") from exc

    return {
        "observation": _to_jsonable(observation),
        "reward": float(reward.value),
        "done": bool(done),
        "info": _to_jsonable(info),
    }


@app.get("/state")
def get_state() -> Dict[str, Any]:
    """Return the full internal environment state in JSON-safe form."""
    try:
        state = _env.state()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"state unavailable: {exc}") from exc
    return _to_jsonable(state)
