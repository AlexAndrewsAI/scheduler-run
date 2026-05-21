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
git clone https://github.com/AlexAndrewsAI/python-package-template.git
cd scheduler-run
uv sync
```

## Usage

### YAML Format

Create a YAML file with a `schedules` key containing a list of entries:
- `type`: The type of command (currently only "system" is supported)
- `command`: The command to execute
- `time`: The time to run the command in 24-hour format (e.g., "14:10")

Example `schedule.yaml`:
```yaml
schedules:
  - type: system
    command: echo 'hello world'
    time: '14:10'
  - type: system
    command: echo 'good morning'
    time: '08:00'
  - type: system
    command: echo 'good night'
    time: '22:00'
```

### Command Line Interface

Run the scheduler using the CLI:

```bash
# Run with default schedule.yaml
uv run scheduler-run

# Run with a custom YAML filefault=Pfault=Pfault=P
uv run scheduler-run --yaml-path path/to/your/schedule.yaml

# Show help
uv run scheduler-run --help
```

### Testing with schedule.yaml

To test the scheduler with the example schedule.yaml file:

```bash
uv run scheduler-run --yaml-path tests/schedule.yaml
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
│   ├uv run scheduler-run ── cli.py
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
uv run scheduler-run 
- **YAML-based scheduling**: Define commands and times in a simuv run scheduler-run uv run scheduler-run ple YAML format
- **Type hints**: Full type annotuv run scheduler-run ations for better IDE support and mypy compatibility
- **Pydantic validation**: Runtime type validation and configuration management
- **CLI interface**: Easy-uv run scheduler-run to-use command line interface with typer
- **Tuv run scheduler-run esting**: Comprehensive test suite with pytest
- **Code quality**: Automated linting with ruff and type checking with mypy
- **Flexible scheduling**: Uses the schedule library for reliable task execution

## Python Best Practices Used

- ✅ **Type hints**: All functions and classes use type annotations
- ✅ **Docstrings**: Clear descriptions of modules, classes, and functions
- ✅ **Project structure**: Proper package layout with separation of concerns
- ✅ **Testing**: Comprehensive test coverage with pytest
- ✅ **Configuration**: Externalized config using pydantic BaseModel
- ✅ **Linting**: Code quality checks with ruff
- ✅ **Dependency management**: Explicit dependencies in pyproject.toml
- ✅ **Python versions**: Supports Python 3.8+


## Disclaimer

This software is intended for personal use and is provided "as is", without any warranty of any kind, express or implied. There is no guarantee that this software is free of bugs or security vulnerabilities. Use it at your own risk.


## License

MIT

## Contributing

This is a template repository. Feel free to use it as a starting point for your own projects.

## Author

AlexAndrewsAI <alex.andrews.ai@protonmail.com>