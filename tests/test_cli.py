"""Tests for the CLI module."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from scheduler_run.cli import app

runner = CliRunner()


def test_run_command_default_path():
    """Test CLI run command with default CSV path."""
    with patch("scheduler_run.cli.Scheduler") as mock_scheduler_class, \
         patch("scheduler_run.cli.Config"):
        mock_scheduler = MagicMock()
        mock_scheduler_class.return_value = mock_scheduler

        result = runner.invoke(app, ["run"])

        if result.exit_code != 0:
            print(f"Exit code: {result.exit_code}")
            print(f"Output: {result.output}")
            print(f"Exception: {result.exception}")
        assert result.exit_code == 0
        mock_scheduler_class.assert_called_once()
        mock_scheduler.run.assert_called_once()


def test_run_command_custom_path():
    """Test CLI run command with custom CSV path."""
    custom_path = "custom/schedule.csv"

    with patch("scheduler_run.cli.Scheduler") as mock_scheduler_class, \
         patch("scheduler_run.cli.Config"):
        mock_scheduler = MagicMock()
        mock_scheduler_class.return_value = mock_scheduler

        result = runner.invoke(app, ["run", "--csv-path", custom_path])

        assert result.exit_code == 0
        mock_scheduler_class.assert_called_once()
        mock_scheduler.run.assert_called_once()


def test_run_command_short_option():
    """Test CLI run command with short option -c."""
    custom_path = "custom/schedule.csv"

    with patch("scheduler_run.cli.Scheduler") as mock_scheduler_class, \
         patch("scheduler_run.cli.Config"):
        mock_scheduler = MagicMock()
        mock_scheduler_class.return_value = mock_scheduler

        result = runner.invoke(app, ["run", "-c", custom_path])

        assert result.exit_code == 0
        mock_scheduler_class.assert_called_once()


def test_app_help():
    """Test CLI help command."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Scheduler" in result.output


def test_run_command_help():
    """Test run command help."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "csv-path" in result.output
