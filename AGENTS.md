# Agent Instructions: scheduler-run

> **Meta-Directive:** As an agent, you are responsible for keeping this file accurate. If you add dependencies, change the project structure, or update the tech stack, you MUST update this file to reflect those changes.

This project is a scheduler that runs commands from a YAML file, built with modern Python practices: `uv` for management, `pydantic` for validation, `typer` for CLI, and `schedule` for task scheduling.

## Tech Stack
- **Environment/Deps:** [uv](https://github.com/astral-sh/uv)
- **Validation:** [pydantic](https://docs.pydantic.dev/)
- **CLI:** [typer](https://typer.tiangolo.com/)
- **Scheduling:** [schedule](https://schedule.readthedocs.io/)
- **Testing:** [pytest](https://docs.pytest.org/)
- **Linting/Formatting:** [ruff](https://beta.ruff.rs/)
- **Type Checking:** [mypy](https://mypy.readthedocs.io/)

## Core Directives
- **Self-Maintenance:** If you modify `pyproject.toml`, the project architecture, or core logic (e.g., renaming `scheduler.py`), immediately update the "Tech Stack", "Workflow Commands", and "Project Structure" sections of this file.
- **Virtual Env:** ALWAYS use the `.venv` directory. Run `uv venv` if it's missing.
- **Python Invocation:** Prefer `python3` or `uv run python`.
- **Pathing:** NEVER use absolute paths. Always use relative paths from the repository root.
- **Isolation:** Do not access files outside the repository parent (`./..`) without explicit permission.
- **Interactivity:** Avoid commands that trigger interactive terminal prompts (e.g., `borg`, `keepass`). For testing, ensure these are mocked or bypassed.
- **Syncing:** Ensure the environment is synced before major operations: `uv sync --dev`.
- **Type Safety:** ALWAYS provide type hints for all function signatures and class members. The project is strictly type-checked with `mypy`.
- **Logging:** NEVER use `print()` for status or debugging. Use the standard `logging` library.
- **Dependencies:** Use `uv add <package>` or `uv remove <package>` to manage dependencies. Do NOT edit `pyproject.toml` manually unless fixing configuration.
- **Testing:** EVERY code change or new feature MUST include corresponding tests in the `tests/` directory. DO NOT RUN pytest, mypy, or ruff check yourself. The user will do this and update you on results.
- **Git Commits:** NEVER stage or commit changes unless explicitly requested by the user.
- **Code Reviews:** When asked to perform a code review, do NOT modify any code. Focus strictly on analysis and recording findings in `./REVIEW.md`.
- **Documentation:** Use Google-style docstrings for all public modules, classes, and functions.

## Workflow Commands
- **Setup:** `uv sync --dev`
- **CLI Dev:** `uv run scheduler-run` (Update this if the package name or CLI entry point changes)

## Project Structure
- `scheduler_run/`: Core logic.
    - `config.py`: Pydantic models for configuration (Config, ScheduleEntry with fields: type, command, time, delay, repetitions, interval).
    - `scheduler.py`: Core scheduling logic.
    - `cli.py`: Typer-based CLI entry point.
- `tests/`: Pytest suite.
- `pyproject.toml`: Dependency and tool configuration.
