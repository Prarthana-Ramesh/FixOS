# FixOS

FixOS is a deterministic OpenEnv-compatible OS troubleshooting environment for evaluating agent reasoning, diagnosis quality, action efficiency, and recovery correctness.

## Environment Description

The environment simulates realistic system administration workflows:

- Process inspection and management
- Service restart and dependency recovery
- Config-file diagnosis and editing
- Disk-pressure mitigation
- Log-based troubleshooting with ambiguous root causes


## OpenEnv Interface

Implemented in `os_simulator/environment.py`:

- `reset(task_id) -> Observation`
- `step(action) -> (Observation, Reward, done, info)`
- `state() -> SystemState`

Typed models are in `os_simulator/models.py`:

- `Action(command: str, args: Optional[str])`
- `Observation(terminal_output: str, last_command: str, step_count: int)`
- `Reward(value: float)`

OpenEnv metadata is provided in `openenv.yaml`.

## Action Space

Supported commands:

- `ps`
- `top`
- `kill <pid>`
- `restart <service>`
- `status <service>`
- `cat <file>`
- `edit <file>`
- `rm <file>`
- `df`
- `logs`

## Observation Space

Each step returns only:

- Terminal output from the last command
- Last command string
- Step count

The agent does not get direct full-state access through observation.

## Tasks

Difficulty families and deterministic variants:

- Easy: `easy_1`, `easy_2`
- Medium: `medium_1`, `medium_2`
- Hard: `hard_1`, `hard_2`, `hard_3`

Aliases:

- `easy` -> `easy_1`
- `medium` -> `medium_1`
- `hard` -> `hard_1`

## Reward and Grading

- Dense reward supports partial progress signals (diagnosis, fixes, service restoration)
- Penalizes inefficient and redundant behavior
- Hard graders evaluate quality dimensions: diagnosis, order, issue resolution, and efficiency
- Scores are clamped to `[0.0, 1.0]`

## Setup

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Run Baseline Inference

`inference.py` has deterministic offline mode enabled by default for reproducible contest scoring.

```powershell
python inference.py
```

Expected stdout format:

```text
[START]
task=easy

[STEP]
action=status nginx
reward=0.1000

[END]
score=1.0000
```

## Optional Online LLM Mode

Set these in `inference.py`:

- `OFFLINE_DETERMINISTIC_BASELINE = False`
- `API_BASE_URL`
- `MODEL_NAME`
- `OPENAI_API_KEY`

## Docker

```powershell
docker build -t fixos-infer .
docker run --rm fixos-infer
```