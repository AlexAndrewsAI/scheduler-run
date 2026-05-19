"""Tests for the scheduler module."""

import logging
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scheduler_run.config import Config
from scheduler_run.scheduler import Scheduler


def test_scheduler_init_default_config() -> None:
    """Test Scheduler initialization with default config."""
    scheduler = Scheduler()
    assert scheduler.config.csv_path == Path("tests/schedule.csv")


def test_scheduler_init_custom_config() -> None:
    """Test Scheduler initialization with custom config."""
    custom_path = Path("custom/schedule.csv")
    config = Config(csv_path=custom_path)
    scheduler = Scheduler(config)
    assert scheduler.config.csv_path == custom_path


def test_run_system_command_success(caplog: pytest.LogCaptureFixture) -> None:
    """Test _run_system_command with a successful command."""
    scheduler = Scheduler()
    caplog.set_level(logging.INFO)

    with patch("scheduler_run.scheduler.subprocess.run") as mock_run:
        scheduler._run_system_command("echo 'test'")
        mock_run.assert_called_once_with(["echo", "test"], check=True)
        assert "Running system command: echo 'test'" in caplog.text


def test_run_system_command_failure(caplog: pytest.LogCaptureFixture) -> None:
    """Test _run_system_command with a failed command."""
    scheduler = Scheduler()
    caplog.set_level(logging.ERROR)

    with patch("scheduler_run.scheduler.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, "false")
        scheduler._run_system_command("false")
        assert "Command failed: false" in caplog.text


def test_schedule_command_system_type(caplog: pytest.LogCaptureFixture) -> None:
    """Test _schedule_command with system type."""
    scheduler = Scheduler()
    caplog.set_level(logging.INFO)

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        scheduler._schedule_command("system", "echo 'test'", "14:30")

        mock_every.assert_called_once()
        mock_day.at.assert_called_once_with("14:30")
        mock_at.do.assert_called_once()
        assert "Scheduled system command 'echo 'test'' at 14:30" in caplog.text


def test_schedule_command_unsupported_type() -> None:
    """Test _schedule_command with unsupported command type."""
    scheduler = Scheduler()

    with pytest.raises(ValueError, match="Unsupported command type: unsupported"):
        scheduler._schedule_command("unsupported", "echo 'test'", "14:30")


def test_load_schedule_success(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule with a valid CSV file."""
    csv_file = tmp_path / "test_schedule.csv"
    csv_file.write_text("type,command,time\nsystem,\"echo 'hello'\",14:10\n")

    config = Config(csv_path=csv_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.INFO)

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        scheduler.load_schedule()

        assert f"Loading schedule from {csv_file}" in caplog.text
        mock_every.assert_called()


def test_load_schedule_file_not_found(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule with a non-existent CSV file."""
    non_existent = tmp_path / "non_existent.csv"
    config = Config(csv_path=non_existent)
    scheduler = Scheduler(config)
    caplog.set_level(logging.ERROR)

    with pytest.raises(FileNotFoundError):
        scheduler.load_schedule()

    assert f"CSV file not found: {non_existent}" in caplog.text


def test_load_schedule_invalid_row(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test load_schedule with invalid CSV rows."""
    csv_file = tmp_path / "invalid_schedule.csv"
    csv_file.write_text(
        "type,command,time\nsystem,\"echo 'hello'\",\n,echo test,14:10\n"
    )

    config = Config(csv_path=csv_file)
    scheduler = Scheduler(config)
    caplog.set_level(logging.WARNING)

    with patch("scheduler_run.scheduler.schedule.every") as mock_every:
        mock_day = MagicMock()
        mock_every.return_value.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        scheduler.load_schedule()

        assert "Skipping invalid row" in caplog.text
