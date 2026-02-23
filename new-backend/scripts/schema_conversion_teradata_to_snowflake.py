"""
Schema conversion: Teradata to Snowflake.

Uses a CSV crosswalk file to replace schema references in SQL files.
"""

from __future__ import annotations

import os
import re
import json
import difflib
import logging
from typing import Callable, Optional

import pandas as pd


def get_logger_for_file(filename: str, log_dir: str = "logs") -> logging.Logger:
    """Create a per-file logger that writes to log_dir/{name}.log."""
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(filename)
    logger.setLevel(logging.INFO)
    if not logger.hasHandlers():
        base = filename.split(".")[0]
        log_filepath = os.path.join(log_dir, f"{base}.log")
        fh = logging.FileHandler(log_filepath)
        fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logger.addHandler(fh)
    return logger


def process_sql_with_pandas_replace(
    csv_file_path: str,
    sql_file_path: str,
    output_dir: str,
    logg: Optional[Callable[[str], None]] = None,
) -> None:
    """
    Apply schema mapping from a CSV crosswalk to SQL files.

    CSV columns expected: SOURCE_SCHEMA, TARGET_DB_SCHEMA.
    SQL files with extensions .sql, .btq, .ddl are processed.
    """
    if logg is None:
        logg = print

    df = pd.read_csv(csv_file_path)
    summary_data: dict = {}

    for filename in os.listdir(sql_file_path):
        summary_file_data = []
        if not filename.endswith((".sql", ".btq", ".ddl")):
            continue

        logger = get_logger_for_file(filename)
        logger.info("Started processing %s", filename)
        logg(f"Started processing {filename}")

        file_path = os.path.join(sql_file_path, filename)
        with open(file_path, "r", encoding="utf-8") as f:
            original_sql = f.read()
            before_change_file = original_sql

        os.makedirs(output_dir, exist_ok=True)
        total_num_matches = 0
        total_num_replacements = 0

        for _, row in df.iterrows():
            old_schema = row["SOURCE_SCHEMA"]
            new_db_schema = row["TARGET_DB_SCHEMA"]

            schema_pattern = rf"\b{old_schema}\b(?=\.)"
            schema_matches = re.findall(schema_pattern, original_sql, flags=re.IGNORECASE)
            schema_num_matches = len(schema_matches)
            total_num_matches += schema_num_matches
            original_sql, schema_num_replacements = re.subn(
                schema_pattern, new_db_schema, original_sql, flags=re.IGNORECASE,
            )
            total_num_replacements += schema_num_replacements

        summary_file_data.append(f"Name of the filename : {filename}")
        summary_file_data.append(f"No of places changes expected : {total_num_matches}")

        after_change_file = original_sql
        before_proc_lines = before_change_file.strip().splitlines()
        after_proc_lines = after_change_file.strip().splitlines()

        diff = difflib.unified_diff(
            before_proc_lines, after_proc_lines,
            fromfile="before_change_file", tofile="after_change_file", lineterm="",
        )

        before_lines = []
        after_lines = []
        for line in diff:
            if line.startswith("-") and not line.startswith("---"):
                before_lines.append(line[1:].strip())
            elif line.startswith("+") and not line.startswith("+++"):
                after_lines.append(line[1:].strip())

        sp_count = 0
        inside_db_count = 0

        for before, after in zip(before_lines, after_lines):
            logger.info("Before: %s", before)
            logg(f"Before: {before}")
            logger.info("After: %s", after)
            logg(f"After: {after}")

            SP_STRING = "REPLACE PROCEDURE"
            if (SP_STRING in before) and (SP_STRING in after):
                if before != after:
                    sp_count += 1
                    if "DB_NOT_FOUND.SCHEMA_NOT_FOUND" in after:
                        logger.info("SP Database not found and Schema not found in cross walk")
                        logg("SP Database not found and Schema not found in cross walk")
                        logger.info("SP DB Change: NO")
                        logg("SP DB Change: NO")
                        total_num_replacements -= 1
                        summary_file_data.append("SP DB Change: NO")
                    else:
                        logger.info("SP DB Change: YES")
                        logg("SP DB Change: YES")
                        summary_file_data.append("SP DB Change: YES")
            else:
                if before != after:
                    inside_db_count += 1
                    if "DB_NOT_FOUND.SCHEMA_NOT_FOUND" in after:
                        logger.info("Inside code Database not found and Schema not found")
                        logg("Inside the code DB Change: NO")
                        total_num_replacements -= 1
                    else:
                        logger.info("Inside the code DB Change: YES")
                        logg("Inside the code DB Change: YES")

        if sp_count == 0:
            logger.info("SP DB Change: NO")
            logg("SP DB Change: NO")
            summary_file_data.append("SP DB Change: NO")

        if total_num_matches != total_num_replacements:
            logger.info("In SP or Inside code Database/Schema not found in cross walk, please check file")
            logg("In SP or Inside code Database/Schema not found in cross walk, please check file")

        summary_file_data.append(f"No of places changes implemented: {total_num_replacements}")
        summary_data[filename] = summary_file_data

        logger.info("Name of the file %s", filename)
        logger.info("Changes required: %d", total_num_matches)
        logger.info("Changes implemented: %d", total_num_replacements)
        logger.info("Finished processing %s", filename)
        logg(f"Finished processing {filename}")

        # Normalize output extension to .sql
        out_name = filename
        if out_name.endswith(".btq"):
            out_name = out_name.replace(".btq", ".sql")
        elif out_name.endswith(".ddl"):
            out_name = out_name.replace(".ddl", ".sql")

        output_file = os.path.join(output_dir, out_name)
        with open(output_file, "w", encoding="utf-8") as out_f:
            out_f.write(original_sql)

    # Write summary JSON
    summary_json_path = os.path.join(output_dir, "summary.json")
    with open(summary_json_path, "w", encoding="utf-8") as json_file:
        json.dump(summary_data, json_file, indent=4)
