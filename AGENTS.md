# Agent Instructions: scheduler-run (Token-Efficient)

## Quick Start
1. **Setup:** Run `uv sync --dev` before major work sessions
2. **Activate:** Ensure `.venv` is active; run `uv venv` if missing
3. **Code:** Use `python3` or `uv run python`; always add type hints and tests

## Tech Stack
| Component | Tool |
|-----------|------|
| Environment & Dependencies | uv |
| Data Validation | Pydantic |
| CLI Framework | Typer |
| Task Scheduling | schedule |
| Testing | pytest |
| Linting & Formatting | ruff |
| Type Checking | mypy |

## Project Structure
```
scheduler_run/
  ├── config.py          (Pydantic models: Config, ScheduleEntry)
  ├── scheduler.py       (Core scheduling logic)
  └── cli.py             (Typer CLI)
tests/                   (Pytest suite)
scripts/                 (Utility scripts, e.g. CSV conversion)
pyproject.toml           (Dependencies & tool config)
```

## Essential Directives

### Code Standards
- **Type Hints:** Required on ALL function signatures and class members. Write code that will pass mypy.
- **Docstrings:** Google-style format for all public APIs.
- **Logging:** Use `logging` module only; never `print()`.
- **Relative Paths:** Never use absolute paths in code.

### Dependency & Configuration Management
- **Adding/Removing Dependencies:** Use `uv add` / `uv remove` commands.
- **Editing pyproject.toml:** Avoid manual edits during development. Only update `pyproject.toml` as the **final change** after all work is tested and finalized.
- **Before Major Work:** Always run `uv sync --dev` first.

### Testing & Quality
- **Test Coverage:** Every code change requires corresponding tests in `tests/`.
- **Manual Validation:** After development is complete, **you will manually run** the full validation suite for final checks.

### Operational Constraints
- **No Interactive Prompts:** Mock or bypass any interactive commands.
- **No Git Operations:** Don't stage/commit unless explicitly requested.
- **Code Review Mode:** Analyze only; record findings in `./REVIEW.md` without making modifications. At the top of the review, identify the reviewer including the name of the IDE/CLI used and the primary model that performed the review.

### File Maintenance
- **Keep Instructions Current:** Update "Tech Stack," "Project Structure," and "Workflow Commands" if `pyproject.toml`, structure, or core logic changes.

## Workflow Commands (Run Manually)
```bash
uv sync --dev                           # Install/sync all dependencies
uv run pytest                           # Run tests (USER RUNS)
uv run ruff check .                     # Lint (USER RUNS)
uv run ruff format .                    # Auto-format (USER RUNS)
uv run mypy .                           # Type check (USER RUNS)
uv run scheduler-run                    # Test CLI
uv run scheduler-run --version          # Show version
```
