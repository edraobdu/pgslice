"""File output handling for SQL dumps."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..utils.logging_config import get_logger

logger = get_logger(__name__)


class SQLWriter:
    """Handles writing SQL dumps to files."""

    @staticmethod
    def write_to_file(sql_content: str, output_path: str | Path) -> None:
        """
        Write SQL content to file.

        Args:
            sql_content: SQL script content
            output_path: Output file path

        Raises:
            IOError: If file cannot be written
        """
        output_path = Path(output_path)

        logger.info(f"Writing SQL to {output_path}")

        try:
            # Ensure parent directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write content
            output_path.write_text(sql_content, encoding="utf-8")

            # Log statistics
            file_size = output_path.stat().st_size
            line_count = sql_content.count("\n")

            logger.info(
                f"Successfully wrote {file_size:,} bytes ({line_count:,} lines) to {output_path}"
            )

        except OSError as e:
            logger.error(f"Failed to write to {output_path}: {e}")
            raise

    @staticmethod
    def generate_default_filename(
        table_name: str, pk_value: str, schema: str = "public"
    ) -> str:
        """
        Generate default filename with timestamp.

        Format: {table}_{pk}_{timestamp}.sql
        Example: users_42_20231223_143052.sql

        Args:
            table_name: Name of the table
            pk_value: Primary key value (sanitized for filename)
            schema: Schema name (default: public)

        Returns:
            Generated filename string
        """
        # Sanitize pk_value for filename (remove special chars)
        safe_pk = str(pk_value).replace("/", "_").replace("\\", "_").replace(" ", "_")

        # Generate timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Build filename
        if schema and schema != "public":
            filename = f"{schema}_{table_name}_{safe_pk}_{timestamp}.sql"
        else:
            filename = f"{table_name}_{safe_pk}_{timestamp}.sql"

        return filename

    @staticmethod
    def get_default_output_path(
        output_dir: Path, table_name: str, pk_value: str, schema: str = "public"
    ) -> Path:
        """
        Get default output path with auto-generated filename.

        Creates output directory if it doesn't exist.

        Args:
            output_dir: Base output directory
            table_name: Name of the table
            pk_value: Primary key value
            schema: Schema name (default: public)

        Returns:
            Full path to output file
        """
        # Ensure directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename
        filename = SQLWriter.generate_default_filename(table_name, pk_value, schema)

        return output_dir / filename

    @staticmethod
    def write_to_stdout(sql_content: str) -> None:
        """
        Write SQL content to stdout.

        Uses sys.stdout directly to avoid print() buffering issues.
        Ensures proper encoding for piping.

        Args:
            sql_content: SQL script content
        """
        import sys

        sys.stdout.write(sql_content)
        sys.stdout.flush()
