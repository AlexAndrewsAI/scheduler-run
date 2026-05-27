# scheduler-run


A scheduler that runs commands from a YAML file at specified times using **uv**, **pydantic**, and the **schedule** library.

## Overview

This is a command scheduler that reads commands from a YAML file and executes them daily at specified times. It demonstrates:

- Modern Python packaging with `pyproject.toml`
- Type hints and static type checking with **mypy**
- Data validation using **pydantic**
- Code linting with **ruff**
- Testing with **pytest**
- Dependency management with **uv**
- Command scheduling with the **schedule** library

The scheduler reads a YAML file with entries containing: `type`, `command`, and `time`, and runs each command daily at the specified time. Scheduled commands run in parallel as background processes; when you stop the scheduler (Ctrl+C), any still-running commands are terminated.

## Installation

### Prerequisites

- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Setup

Clone the repository and install dependencies:

```bash
git clone https://github.com/AlexAndrewsAI/scheduler-run.git
cd scheduler-run
uv sync
```

## Usage

### YAML Format

Create a YAML file with a `schedules` key containing a list of entries:
- `type`: The type of command (currently only "system" is supported)
- `command`: The command to execute
- `time`: The time to run the command in 24-hour H:MM or HH:MM format (e.g., "14:10" or "9:00"). Single-digit hours are accepted and normalised to zero-padded HH:MM on load.
- `delay`: The base delay in seconds (optional, defaults to 0). If specified, a random start delay is calculated based on a gaussian distribution: `max(0, int(random.gauss(mu=delay, sigma=0.15 * delay)))`
- `repetitions`: Number of times to repeat the command (optional, defaults to 0). If greater than 0, the command will run `repetitions + 1` times total.
- `interval`: Time offset in seconds from the base time for each repetition (optional, defaults to -1). Only used when `repetitions > 0`. The timing for repetition `i` is calculated as `base_time + (i * interval) + delay_i`, where `delay_i` is a random delay recalculated for each execution. If set to -1 and `repetitions > 0`, the interval is auto-calculated to spread runs evenly throughout the day: `24*3600 / (repetitions + 1)`

Example `schedule.yaml`:
```yaml
schedules:
  - type: system
    command: echo 'hello world'
    time: '14:10'
    delay: 10
  - type: system
    command: echo 'good morning'
    time: '08:00'
    delay: 0
  - type: system
    command: echo 'good night'
    time: '22:00'
  - type: system
    command: echo 'repeated task'
    time: '09:00'
    repetitions: 3
    interval: 3600
```

### Command Line Interface

Run the scheduler using the CLI:

```bash
# Run with default schedule.yaml
uv run scheduler-run

# Run with a custom YAML file (positional argument)
uv run scheduler-run path/to/your/schedule.yaml

# Run with multiple YAML files
uv run scheduler-run schedule1.yaml schedule2.yaml

# Allow duplicate schedule entries
uv run scheduler-run --allow-duplicates schedule.yaml

# Limit concurrent subprocesses (prevents resource exhaustion, default: 5)
uv run scheduler-run --max-concurrent 10 schedule.yaml

# Set unlimited concurrent subprocesses
uv run scheduler-run --max-concurrent null schedule.yaml

# Show version
uv run scheduler-run --version

# Show help
uv run scheduler-run --help

# Run as a module
uv run python -m scheduler_run
```

### Testing with schedule.yaml

To test the scheduler with the example schedule.yaml file:

```bash
uv run scheduler-run tests/schedule.yaml
```

The scheduler will load the commands from the YAML file and run them at the specified times. Commands that overlap in time run in parallel. Press Ctrl+C to stop the scheduler; any commands still running are terminated.

### Python API

You can also use the scheduler programmatically:

```python
from scheduler_run.scheduler import Scheduler
from scheduler_run.config import Config

# Create a scheduler with default config (max_concurrent=5)
scheduler = Scheduler()

# Or with custom config
config = Config(yaml_path="path/to/schedule.yaml")
scheduler = Scheduler(config)

# Or with custom max_concurrent limit
config = Config(yaml_path="path/to/schedule.yaml", max_concurrent=10)
scheduler = Scheduler(config)

# Or with unlimited concurrent subprocesses
config = Config(yaml_path="path/to/schedule.yaml", max_concurrent=None)
scheduler = Scheduler(config)

# Run the scheduler (blocks indefinitely)
scheduler.run()
```

## Development

### Install Dev Dependencies

```bash
uv sync --dev
```

This installs all dependencies and dev tools (pytest, pytest-cov, ruff, mypy).

### Run Tests

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Show print statements during tests
uv run pytest -s
```

### Code Quality

```bash
# Lint and format
uv run ruff check .
uv run ruff format .

# Type check
uv run mypy .
```

Tests enforce at least 80% coverage on `scheduler_run` via pytest-cov.

## Project Structure

```
scheduler-run/
├── .github/workflows/ci.yml
├── AGENTS.md
├── pyproject.toml
├── scheduler_run/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── config.py
│   └── scheduler.py
├── scripts/
│   └── convert_csv_to_yaml.py
└── tests/
    ├── test_cli.py
    ├── test_config.py
    ├── test_scheduler.py
    └── schedule.yaml
```

## Features
- **YAML-based scheduling**: Define commands and times in a simple YAML format
- **Type hints**: Full type annotations for better IDE support and mypy compatibility
- **Pydantic validation**: Runtime type validation and configuration management
- **CLI interface**: Easy-to-use command line interface with typer
- **Testing**: Comprehensive test suite with pytest
- **Code quality**: Automated linting with ruff and type checking with mypy
- **Flexible scheduling**: Uses the schedule library for reliable task execution
- **Parallel execution**: Overlapping scheduled commands run concurrently as subprocesses
- **Concurrency limiting**: Built-in max_concurrent limit (default: 5) prevents resource exhaustion by queuing commands when the limit is reached
- **Clean shutdown**: Stopping the scheduler terminates any child processes still running

## Security Considerations

**Important:** This scheduler executes commands defined in YAML files. Please ensure:

- YAML files are from trusted sources
- YAML files have appropriate file permissions (e.g., `600` for sensitive schedules)
- Commands in YAML files are reviewed before deployment
- The scheduler runs with the minimum necessary system privileges

The scheduler uses `shell=False` for subprocess execution, which provides some protection against shell injection, but arbitrary commands can still be executed based on YAML file contents.

## Disclaimer

This software is intended for personal use and is provided "as is", without any warranty of any kind, express or implied. There is no guarantee that this software is free of bugs or security vulnerabilities. Use it at your own risk.


## License

MIT


## Author

AlexAndrewsAI <alex.andrews.ai@protonmail.com>