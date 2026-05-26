"""Tests for the CSV to YAML converter script."""

from pathlib import Path

import pytest
import yaml

from scripts.convert_csv_to_yaml import convert_csv_to_yaml


def test_convert_csv_to_yaml_valid(tmp_path: Path) -> None:
    """Test converting a valid CSV file to YAML."""
    csv_file = tmp_path / "schedule.csv"
    yaml_file = tmp_path / "schedule.yaml"

    csv_content = """type,command,time,delay,repetitions,interval
system,echo 'hello',14:30,10,0,-1
system,echo 'world',09:00,0,3,60
"""
    csv_file.write_text(csv_content)

    convert_csv_to_yaml(csv_file, yaml_file)

    assert yaml_file.exists()

    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    assert "schedules" in data
    assert len(data["schedules"]) == 2

    # Check first entry
    entry1 = data["schedules"][0]
    assert entry1["type"] == "system"
    assert entry1["command"] == "echo 'hello'"
    assert entry1["time"] == "14:30"
    assert entry1["delay"] == 10
    assert entry1["repetitions"] == 0
    assert entry1["interval"] == -1

    # Check second entry
    entry2 = data["schedules"][1]
    assert entry2["type"] == "system"
    assert entry2["command"] == "echo 'world'"
    assert entry2["time"] == "09:00"
    assert entry2["delay"] == 0
    assert entry2["repetitions"] == 3
    assert entry2["interval"] == 60


def test_convert_csv_to_yaml_invalid_time(tmp_path: Path) -> None:
    """Test that invalid time format is rejected."""
    csv_file = tmp_path / "schedule.csv"
    yaml_file = tmp_path / "schedule.yaml"

    csv_content = """type,command,time
system,echo 'hello',25:00
system,echo 'world',14:30
"""
    csv_file.write_text(csv_content)

    convert_csv_to_yaml(csv_file, yaml_file)

    assert yaml_file.exists()

    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    # Only the valid entry should be included
    assert len(data["schedules"]) == 1
    assert data["schedules"][0]["command"] == "echo 'world'"


def test_convert_csv_to_yaml_invalid_type(tmp_path: Path) -> None:
    """Test that invalid type is rejected."""
    csv_file = tmp_path / "schedule.csv"
    yaml_file = tmp_path / "schedule.yaml"

    csv_content = """type,command,time
unsupported,echo 'hello',14:30
system,echo 'world',14:30
"""
    csv_file.write_text(csv_content)

    convert_csv_to_yaml(csv_file, yaml_file)

    assert yaml_file.exists()

    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    # Only the valid entry should be included
    assert len(data["schedules"]) == 1
    assert data["schedules"][0]["type"] == "system"


def test_convert_csv_to_yaml_empty_command(tmp_path: Path) -> None:
    """Test that empty command is rejected."""
    csv_file = tmp_path / "schedule.csv"
    yaml_file = tmp_path / "schedule.yaml"

    csv_content = """type,command,time
system,,14:30
system,echo 'world',14:30
"""
    csv_file.write_text(csv_content)

    convert_csv_to_yaml(csv_file, yaml_file)

    assert yaml_file.exists()

    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    # Only the valid entry should be included
    assert len(data["schedules"]) == 1
    assert data["schedules"][0]["command"] == "echo 'world'"


def test_convert_csv_to_yaml_negative_delay(tmp_path: Path) -> None:
    """Test that negative delay is rejected."""
    csv_file = tmp_path / "schedule.csv"
    yaml_file = tmp_path / "schedule.yaml"

    csv_content = """type,command,time,delay
system,echo 'hello',14:30,-5
system,echo 'world',14:30,10
"""
    csv_file.write_text(csv_content)

    convert_csv_to_yaml(csv_file, yaml_file)

    assert yaml_file.exists()

    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    # Only the valid entry should be included
    assert len(data["schedules"]) == 1
    assert data["schedules"][0]["command"] == "echo 'world'"


def test_convert_csv_to_yaml_negative_repetitions(tmp_path: Path) -> None:
    """Test that negative repetitions is rejected."""
    csv_file = tmp_path / "schedule.csv"
    yaml_file = tmp_path / "schedule.yaml"

    csv_content = """type,command,time,repetitions
system,echo 'hello',14:30,-3
system,echo 'world',14:30,5
"""
    csv_file.write_text(csv_content)

    convert_csv_to_yaml(csv_file, yaml_file)

    assert yaml_file.exists()

    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    # Only the valid entry should be included
    assert len(data["schedules"]) == 1
    assert data["schedules"][0]["command"] == "echo 'world'"


def test_convert_csv_to_yaml_invalid_interval_with_repetitions(tmp_path: Path) -> None:
    """Test that invalid interval with repetitions is rejected."""
    csv_file = tmp_path / "schedule.csv"
    yaml_file = tmp_path / "schedule.yaml"

    csv_content = """type,command,time,repetitions,interval
system,echo 'hello',14:30,3,0
system,echo 'world',14:30,3,60
"""
    csv_file.write_text(csv_content)

    convert_csv_to_yaml(csv_file, yaml_file)

    assert yaml_file.exists()

    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    # Only the valid entry should be included
    assert len(data["schedules"]) == 1
    assert data["schedules"][0]["command"] == "echo 'world'"


def test_convert_csv_to_yaml_missing_optional_fields(tmp_path: Path) -> None:
    """Test that missing optional fields use defaults."""
    csv_file = tmp_path / "schedule.csv"
    yaml_file = tmp_path / "schedule.yaml"

    csv_content = """type,command,time
system,echo 'hello',14:30
"""
    csv_file.write_text(csv_content)

    convert_csv_to_yaml(csv_file, yaml_file)

    assert yaml_file.exists()

    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    assert len(data["schedules"]) == 1
    entry = data["schedules"][0]
    assert entry["delay"] == 0
    assert entry["repetitions"] == 0
    assert entry["interval"] == -1


def test_convert_csv_to_yaml_creates_parent_directories(tmp_path: Path) -> None:
    """Test that parent directories are created if they don't exist."""
    csv_file = tmp_path / "schedule.csv"
    yaml_file = tmp_path / "subdir" / "schedule.yaml"

    csv_content = """type,command,time
system,echo 'hello',14:30
"""
    csv_file.write_text(csv_content)

    convert_csv_to_yaml(csv_file, yaml_file)

    assert yaml_file.exists()
    assert yaml_file.parent.exists()


def test_convert_csv_to_yaml_file_not_found(tmp_path: Path) -> None:
    """Test that FileNotFoundError is raised for missing CSV file."""
    csv_file = tmp_path / "nonexistent.csv"
    yaml_file = tmp_path / "schedule.yaml"

    with pytest.raises(FileNotFoundError):
        convert_csv_to_yaml(csv_file, yaml_file)


def test_convert_csv_to_yaml_empty_csv(tmp_path: Path) -> None:
    """Test converting an empty CSV file (no rows)."""
    csv_file = tmp_path / "schedule.csv"
    yaml_file = tmp_path / "schedule.yaml"

    csv_content = """type,command,time
"""
    csv_file.write_text(csv_content)

    convert_csv_to_yaml(csv_file, yaml_file)

    assert yaml_file.exists()

    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    assert "schedules" in data
    assert len(data["schedules"]) == 0


def test_convert_csv_to_yaml_all_invalid_rows(tmp_path: Path) -> None:
    """Test that all invalid rows result in empty schedules."""
    csv_file = tmp_path / "schedule.csv"
    yaml_file = tmp_path / "schedule.yaml"

    csv_content = """type,command,time
invalid,echo 'hello',14:30
system,,14:30
system,echo 'world',25:00
"""
    csv_file.write_text(csv_content)

    convert_csv_to_yaml(csv_file, yaml_file)

    assert yaml_file.exists()

    with open(yaml_file) as f:
        data = yaml.safe_load(f)

    assert len(data["schedules"]) == 0
