"""Tests for the config module."""

from pathlib import Path

from scheduler_run.config import Config


def test_config_default():
    """Test Config with default values."""
    config = Config()
    assert config.csv_path == Path("tests/schedule.csv")


def test_config_custom_path():
    """Test Config with custom csv_path."""
    custom_path = Path("custom/schedule.csv")
    config = Config(csv_path=custom_path)
    assert config.csv_path == custom_path


def test_config_model_title():
    """Test Config model title."""
    config = Config()
    assert config.model_config["title"] == "Scheduler Config"
