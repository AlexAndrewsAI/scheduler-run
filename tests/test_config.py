"""Tests for the config module."""

from pathlib import Path

import pytest

from scheduler_run.config import Config, ScheduleEntry


def test_config_default() -> None:
    """Test Config with default values."""
    config = Config()
    assert config.yaml_path == Path("tests/schedule.yaml")


def test_config_custom_path() -> None:
    """Test Config with custom yaml_path."""
    custom_path = Path("custom/schedule.yaml")
    config = Config(yaml_path=custom_path)
    assert config.yaml_path == custom_path


def test_config_model_title() -> None:
    """Test Config model title."""
    config = Config()
    assert config.model_config["title"] == "Scheduler Config"


def test_schedule_entry_valid() -> None:
    """Test ScheduleEntry with valid data."""
    entry = ScheduleEntry(type="system", command="echo 'hello'", time="14:30")
    assert entry.type == "system"
    assert entry.command == "echo 'hello'"
    assert entry.time == "14:30"


def test_schedule_entry_valid_time_formats() -> None:
    """Test ScheduleEntry with various valid time formats."""
    valid_times = ["00:00", "01:00", "09:00", "12:00", "13:00", "23:59", "08:00"]
    for time_str in valid_times:
        entry = ScheduleEntry(type="system", command="echo test", time=time_str)
        assert entry.time == time_str


def test_schedule_entry_invalid_time_format() -> None:
    """Test ScheduleEntry with invalid time format."""
    invalid_times = ["24:00", "25:00", "14:60", "14:9", "14", "14:30:00", "ab:cd"]
    for time_str in invalid_times:
        with pytest.raises(ValueError, match="Invalid time format"):
            ScheduleEntry(type="system", command="echo test", time=time_str)


def test_schedule_entry_empty_command() -> None:
    """Test ScheduleEntry with empty command."""
    with pytest.raises(ValueError, match="Command cannot be empty"):
        ScheduleEntry(type="system", command="", time="14:30")

    with pytest.raises(ValueError, match="Command cannot be empty"):
        ScheduleEntry(type="system", command="   ", time="14:30")


def test_schedule_entry_empty_type() -> None:
    """Test ScheduleEntry with empty type."""
    with pytest.raises(ValueError, match="Type cannot be empty"):
        ScheduleEntry(type="", command="echo test", time="14:30")

    with pytest.raises(ValueError, match="Type cannot be empty"):
        ScheduleEntry(type="   ", command="echo test", time="14:30")
