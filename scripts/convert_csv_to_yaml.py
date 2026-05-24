#!/usr/bin/env python3
"""Convert CSV schedule file to YAML format.

This script converts a CSV file with columns: type, command, time, delay, repetitions, interval
to a YAML file with the equivalent structure.
"""

import argparse
import csv
import logging
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def convert_csv_to_yaml(csv_path: Path, yaml_path: Path) -> None:
    """Convert CSV schedule file to YAML format.

    Args:
        csv_path: Path to the input CSV file.
        yaml_path: Path to the output YAML file.

    """
    logger.info(f"Reading CSV from {csv_path}")

    schedules = []

    try:
        with open(csv_path, newline="") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                entry = {
                    "type": row.get("type", "").strip(),
                    "command": row.get("command", "").strip(),
                    "time": row.get("time", "").strip(),
                }
                
                # Handle optional fields with defaults
                delay_str = row.get("delay", "").strip()
                if delay_str:
                    try:
                        entry["delay"] = int(delay_str)
                    except ValueError:
                        logger.warning(f"Invalid delay value '{delay_str}', using default 0")
                        entry["delay"] = 0
                
                repetitions_str = row.get("repetitions", "").strip()
                if repetitions_str:
                    try:
                        entry["repetitions"] = int(repetitions_str)
                    except ValueError:
                        logger.warning(f"Invalid repetitions value '{repetitions_str}', using default 0")
                        entry["repetitions"] = 0
                
                interval_str = row.get("interval", "").strip()
                if interval_str:
                    try:
                        entry["interval"] = int(interval_str)
                    except ValueError:
                        logger.warning(f"Invalid interval value '{interval_str}', using default -1")
                        entry["interval"] = -1
                
                if entry["type"] and entry["command"] and entry["time"]:
                    schedules.append(entry)
                else:
                    logger.warning(f"Skipping incomplete row: {row}")
    except FileNotFoundError:
        logger.error(f"CSV file not found: {csv_path}")
        raise
    except csv.Error as e:
        logger.error(f"CSV parsing error: {e}")
        raise

    yaml_data = {"schedules": schedules}

    logger.info(f"Writing YAML to {yaml_path}")
    yaml_path.parent.mkdir(parents=True, exist_ok=True)

    with open(yaml_path, "w") as yamlfile:
        yaml.dump(yaml_data, yamlfile, default_flow_style=False, sort_keys=False)

    logger.info(f"Successfully converted {len(schedules)} schedule entries")


def main() -> None:
    """Main entry point for the conversion script."""
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
