"""Node: Apply schema mapping using CSV crosswalk."""

from __future__ import annotations

import os
import shutil
import logging
from datetime import datetime

from graph.state import MigrationContext, MigrationState
from graph.nodes.helpers import log_event, is_error_state, read_sql_files

logger = logging.getLogger(__name__)


def apply_schema_mapping_node(state: MigrationContext) -> MigrationContext:
    """
    Apply schema mapping using process_sql_with_pandas_replace.

    Reads the CSV crosswalk, processes all SQL files in the source directory,
    and replaces the source directory with the mapped output.
    """
    if is_error_state(state):
        return state

    logger.info("Applying schema mapping for project: %s", state.project_name)
    log_event(state, "info", f"Applying schema mapping for project: {state.project_name}")

    try:
        from scripts.schema_conversion_teradata_to_snowflake import process_sql_with_pandas_replace

        source_dir = os.path.join(state.project_path, "source")
        mapped_dir = os.path.join(state.project_path, "source_mapped")
        os.makedirs(mapped_dir, exist_ok=True)

        def log_callback(msg):
            state.warnings.append(str(msg))
            logger.info("Schema mapping: %s", msg)
            log_event(state, "info", f"Schema mapping: {msg}")

        process_sql_with_pandas_replace(
            csv_file_path=state.mapping_csv_path,
            sql_file_path=source_dir,
            output_dir=mapped_dir,
            logg=log_callback,
        )

        # Replace original source with mapped source
        if os.path.isdir(source_dir):
            shutil.rmtree(source_dir)
        if os.path.isdir(mapped_dir):
            shutil.move(mapped_dir, source_dir)
        else:
            os.makedirs(source_dir, exist_ok=True)
            warning_msg = f"Mapped output directory not found: {mapped_dir}"
            state.warnings.append(warning_msg)
            log_event(state, "warning", warning_msg)

        state.current_stage = MigrationState.APPLY_SCHEMA_MAPPING
        state.updated_at = datetime.now()
        logger.info("Schema mapping applied successfully")
        log_event(state, "info", "Schema mapping applied successfully")

        state.schema_mapped_code = read_sql_files(source_dir)

    except Exception as e:
        error_msg = f"Exception during schema mapping: {e}"
        logger.error(error_msg)
        state.errors.append(error_msg)
        state.current_stage = MigrationState.ERROR
        log_event(state, "error", error_msg)

    return state
