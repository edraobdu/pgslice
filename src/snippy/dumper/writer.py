"""File output handling for SQL dumps."""

from __future__ import annotations

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
    def write_to_stdout(sql_content: str) -> None:
        """
        Write SQL content to stdout.

        Args:
            sql_content: SQL script content
        """
        logger.debug("Writing SQL to stdout")
