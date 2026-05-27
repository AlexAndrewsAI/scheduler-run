"""Tests for the CSV to YAML conversion script."""

import logging
from pathlib import Path

import pytest
import yaml

from scripts.convert_csv_to_yaml import convert_csv_to_yaml


def test_convert_csv_to_yaml_basic(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test basic CSV to YAML conversion."""
    csv_file = tmp_path / "schedule.csv"
    csv_file.write_text(
        "type,command,time\nsystem,echo 'hello',14:10\nsystem,echo 'goodbye',15:00\n"
    )

    yaml_file = tmp_path / "schedule.yaml"
    caplog.set_level(logging.INFO)

    convert_csv_to_yaml(csv_file, yaml_file)

    assert yaml_file.exists()
    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    assert data["schedules"] == [
        {
            "type": "system",
            "command": "echo 'hello'",
            "time": "14:10",
            "delay": 0,
            "variables": None,
            "repetitions": 0,
            "interval": -1,
            "max_runtime": None,
        },
        {
            "type": "system",
            "command": "echo 'goodbye'",
            "time": "15:00",
            "delay": 0,
            "variables": None,
            "repetitions": 0,
            "interval": -1,
            "max_runtime": None,
        },
    ]
    assert "Successfully converted 2 schedule entries" in caplog.text


def test_convert_csv_with_optional_fields(tmp_path: Path) -> None:
    """Test CSV conversion with delay, repetitions, and interval fields."""
    csv_file = tmp_path / "schedule.csv"
    csv_file.write_text(
        "type,command,time,delay,repetitions,interval\n"
        "system,echo 'hello',14:10,10,3,3600\n"
        "system,echo 'goodbye',15:00,0,0,-1\n"
    )

    yaml_file = tmp_path / "schedule.yaml"
    convert_csv_to_yaml(csv_file, yaml_file)

    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    assert data["schedules"] == [
        {
            "type": "system",
            "command": "echo 'hello'",
            "time": "14:10",
            "delay": 10,
            "variables": None,
            "repetitions": 3,
            "interval": 3600,
            "max_runtime": None,
        },
        {
            "type": "system",
            "command": "echo 'goodbye'",
            "time": "15:00",
            "delay": 0,
            "variables": None,
            "repetitions": 0,
            "interval": -1,
            "max_runtime": None,
        },
    ]


def test_convert_csv_missing_optional_fields(tmp_path: Path) -> None:
    """Test CSV conversion when optional fields are missing."""
    csv_file = tmp_path / "schedule.csv"
    csv_file.write_text("type,command,time\nsystem,echo 'hello',14:10\n")

    yaml_file = tmp_path / "schedule.yaml"
    convert_csv_to_yaml(csv_file, yaml_file)

    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    # Optional fields are now included with default values from ScheduleEntry
    entry = data["schedules"][0]
    assert entry["delay"] == 0
    assert entry["variables"] is None
    assert entry["repetitions"] == 0
    assert entry["interval"] == -1


def test_convert_csv_empty_optional_fields(tmp_path: Path) -> None:
    """Test CSV conversion when optional fields are empty strings."""
    csv_file = tmp_path / "schedule.csv"
    csv_file.write_text(
        "type,command,time,delay,repetitions,interval\nsystem,echo 'hello',14:10,,, \n"
    )

    yaml_file = tmp_path / "schedule.yaml"
    convert_csv_to_yaml(csv_file, yaml_file)

    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    # Empty optional fields are now included with default values from ScheduleEntry
    entry = data["schedules"][0]
    assert entry["delay"] == 0
    assert entry["variables"] is None
    assert entry["repetitions"] == 0
    assert entry["interval"] == -1


def test_convert_csv_invalid_delay(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test CSV conversion with invalid delay value."""
    csv_file = tmp_path / "schedule.csv"
    csv_file.write_text("type,command,time,delay\nsystem,echo 'hello',14:10,invalid\n")

    yaml_file = tmp_path / "schedule.yaml"
    caplog.set_level(logging.WARNING)

    convert_csv_to_yaml(csv_file, yaml_file)

    assert "Invalid delay value 'invalid', using default 0" in caplog.text
    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    assert data["schedules"][0]["delay"] == 0


def test_convert_csv_invalid_repetitions(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test CSV conversion with invalid repetitions value."""
    csv_file = tmp_path / "schedule.csv"
    csv_file.write_text(
        "type,command,time,repetitions\nsystem,echo 'hello',14:10,abc\n"
    )

    yaml_file = tmp_path / "schedule.yaml"
    caplog.set_level(logging.WARNING)

    convert_csv_to_yaml(csv_file, yaml_file)

    assert "Invalid repetitions value 'abc', using default 0" in caplog.text
    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    assert data["schedules"][0]["repetitions"] == 0


def test_convert_csv_invalid_interval(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test CSV conversion with invalid interval value."""
    csv_file = tmp_path / "schedule.csv"
    csv_file.write_text(
        "type,command,time,interval\nsystem,echo 'hello',14:10,notanumber\n"
    )

    yaml_file = tmp_path / "schedule.yaml"
    caplog.set_level(logging.WARNING)

    convert_csv_to_yaml(csv_file, yaml_file)

    assert "Invalid interval value 'notanumber', using default -1" in caplog.text
    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    assert data["schedules"][0]["interval"] == -1


def test_convert_csv_incomplete_row(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test CSV conversion with incomplete row (missing required fields)."""
    csv_file = tmp_path / "schedule.csv"
    csv_file.write_text(
        "type,command,time\n"
        "system,echo 'hello',14:10\n"
        "system,,15:00\n"
        "system,echo 'test',\n"
    )

    yaml_file = tmp_path / "schedule.yaml"
    caplog.set_level(logging.WARNING)

    convert_csv_to_yaml(csv_file, yaml_file)

    assert "Validation failed" in caplog.text
    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    # Only the complete row should be converted
    assert len(data["schedules"]) == 1
    assert data["schedules"][0]["command"] == "echo 'hello'"


def test_convert_csv_empty_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Test CSV conversion with empty file (only header)."""
    csv_file = tmp_path / "schedule.csv"
    csv_file.write_text("type,command,time\n")

    yaml_file = tmp_path / "schedule.yaml"
    caplog.set_level(logging.INFO)

    convert_csv_to_yaml(csv_file, yaml_file)

    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    assert data["schedules"] == []
    assert "Successfully converted 0 schedule entries" in caplog.text


def test_convert_csv_file_not_found(tmp_path: Path) -> None:
    """Test CSV conversion when file doesn't exist."""
    csv_file = tmp_path / "nonexistent.csv"
    yaml_file = tmp_path / "schedule.yaml"

    with pytest.raises(FileNotFoundError):
        convert_csv_to_yaml(csv_file, yaml_file)


def test_convert_csv_creates_parent_dirs(tmp_path: Path) -> None:
    """Test CSV conversion creates parent directories if needed."""
    csv_file = tmp_path / "schedule.csv"
    csv_file.write_text("type,command,time\nsystem,echo 'test',14:10\n")

    yaml_file = tmp_path / "subdir" / "nested" / "schedule.yaml"

    convert_csv_to_yaml(csv_file, yaml_file)

    assert yaml_file.exists()
    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    assert len(data["schedules"]) == 1


def test_convert_csv_whitespace_handling(tmp_path: Path) -> None:
    """Test CSV conversion handles whitespace in fields."""
    csv_file = tmp_path / "schedule.csv"
    csv_file.write_text("type,command,time\n  system  ,  echo 'hello'  ,  14:10  \n")

    yaml_file = tmp_path / "schedule.yaml"
    convert_csv_to_yaml(csv_file, yaml_file)

    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    assert data["schedules"][0]["type"] == "system"
    assert data["schedules"][0]["command"] == "echo 'hello'"
    assert data["schedules"][0]["time"] == "14:10"
