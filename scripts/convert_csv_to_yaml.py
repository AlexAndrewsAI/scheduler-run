#!/usr/bin/env python3
"""Convert CSV schedule file to YAML format.

This script converts a CSV file with columns: type, command, time, delay,
repetitions, interval to a YAML file with the equivalent structure.
"""

import argparse
import csv
import logging
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

# Add parent directory to path to import scheduler_run module
sys.path.insert(0, str(Path(__file__).parent.parent))

from scheduler_run.config import ScheduleEntry

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _parse_optional_int(row: dict, key: str, default: int) -> int:
    """Parse an optional integer field from a CSV row.

    Args:
        row: The CSV row dictionary.
        key: The field name to parse.
        default: The default value if the field is missing or invalid.

    Returns:
        The parsed integer value or the default.

    """
    value_str = row.get(key, "").strip()
    if value_str:
        try:
            return int(value_str)
        except ValueError:
            logger.warning(
                "Invalid %s value '%s', using default %s", key, value_str, default
            )
            return default
    return default


def convert_csv_to_yaml(csv_path: Path, yaml_path: Path) -> None:
    """Convert CSV schedule file to YAML format.

    Args:
        csv_path: Path to the input CSV file.
        yaml_path: Path to the output YAML file.

    """
    logger.info("Reading CSV from %s", csv_path)

    schedules = []
    validation_errors = 0

    try:
        with open(csv_path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row_num, row in enumerate(reader, start=1):
                entry = {
                    "type": row.get("type", "").strip(),
                    "command": row.get("command", "").strip(),
                    "time": row.get("time", "").strip(),
                }

                # Handle optional fields with defaults
                delay_str = row.get("delay", "").strip()
                if delay_str:
                    delay = _parse_optional_int(row, "delay", 0)
                    entry["delay"] = delay

                repetitions_str = row.get("repetitions", "").strip()
                if repetitions_str:
                    repetitions = _parse_optional_int(row, "repetitions", 0)
                    entry["repetitions"] = repetitions

                interval_str = row.get("interval", "").strip()
                if interval_str:
                    interval = _parse_optional_int(row, "interval", -1)
                    entry["interval"] = interval

                # Validate using ScheduleEntry
                try:
                    validated_entry = ScheduleEntry(**entry)
                    schedules.append(validated_entry.model_dump())
                except ValidationError as e:
                    validation_errors += 1
                    logger.error("Row %s: Validation failed - %s", row_num, e)
                except ValueError as e:
                    validation_errors += 1
                    logger.error("Row %s: Validation failed - %s", row_num, e)
    except FileNotFoundError:
        logger.error("CSV file not found: %s", csv_path)
        raise
    except csv.Error as e:
        logger.error("CSV parsing error: %s", e)
        raise

    yaml_data = {"schedules": schedules}

    logger.info("Writing YAML to %s", yaml_path)
    yaml_path.parent.mkdir(parents=True, exist_ok=True)

    with open(yaml_path, "w") as yamlfile:
        yaml.dump(yaml_data, yamlfile, default_flow_style=False, sort_keys=False)

    logger.info(
        "Successfully converted %s schedule entries (%s validation errors)",
        len(schedules),
        validation_errors,
    )

    if validation_errors > 0:
        logger.warning(
            "%s row(s) failed validation and were not included in the output",
            validation_errors,
        )


def main() -> None:
    """Run the conversion script."""
    parser = argparse.ArgumentParser(
        description="Convert CSV schedule file to YAML format"
    )
    parser.add_argument(
        "csv_file",
        type=Path,
        help="Path to the input CSV file",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Path to the output YAML file (default: <csv_file>.yaml)",
    )

    args = parser.parse_args()

    if args.output is None:
        yaml_path = args.csv_file.with_suffix(".yaml")
    else:
        yaml_path = args.output

    convert_csv_to_yaml(args.csv_file, yaml_path)


if __name__ == "__main__":
    main()
