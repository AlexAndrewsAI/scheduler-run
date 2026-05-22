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

The scheduler reads a YAML file with entries containing: `type`, `command`, and `time`, and runs each command daily at the specified time.

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
- `time`: The time to run the command in 24-hour format (e.g., "14:10")
- `delay`: The base delay in seconds (optional, defaults to 0). If specified, a random start delay is calculated based on a gaussian distribution: `max(0, int(random.gauss(mu=delay, sigma=0.15 * delay)))`
- `repetitions`: Number of times to repeat the command (optional, defaults to 0). If greater than 0, the command will run `repetitions + 1` times total.
- `interval`: Time in seconds between repetitions (optional, defaults to -1). Only used when `repetitions > 0`. If set to -1 and `repetitions > 0`, the interval is auto-calculated to spread runs evenly throughout the day: `24*3600 / (repetitions + 1)`

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

# Show help
uv run scheduler-run --help
```

### Testing with schedule.yaml

To test the scheduler with the example schedule.yaml file:

```bash
uv run scheduler-run tests/schedule.yaml
```

The scheduler will load the commands from the YAML file and run them at the specified times. Press Ctrl+C to stop the scheduler.

### Python API

You can also use the scheduler programmatically:

```python
from scheduler_run.scheduler import Scheduler
from scheduler_run.config import Config

# Create a scheduler with default config
scheduler = Scheduler()

# Or with custom config
config = Config(yaml_path="path/to/schedule.yaml")
scheduler = Scheduler(config)

# Run the scheduler (blocks indefinitely)
scheduler.run()
```

## Development

### Install Dev Dependencies

```bash
uv sync
```

This installs all dependencies and dev tools (pytest, ruff, mypy).

### Run Tests

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v
uv run scheduler-run 
# Show print statements during tests
uv run pytest -s
```

### Code Quality

```bash
# Lint code
uv run ruff check scheduler_run tests

# Type check
uv run mypy scheduler_run
```

## Project Structure

```
scheduler-run/
├── .gitignore
├── pyproject.toml
├── README.md
├── scheduler_run/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   └── scheduler.py
└── tests/
    ├── __init__.py
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

## Disclaimer

This software is intended for personal use and is provided "as is", without any warranty of any kind, express or implied. There is no guarantee that this software is free of bugs or security vulnerabilities. Use it at your own risk.


## License

MIT


## Author

AlexAndrewsAI <alex.andrews.ai@protonmail.com>