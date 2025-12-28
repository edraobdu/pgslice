"""Shared parsing utilities for CLI and REPL."""

from __future__ import annotations

from datetime import datetime

from pgslice.graph.models import TimeframeFilter
from pgslice.utils.exceptions import InvalidTimeframeError


def parse_truncate_filter(spec: str) -> TimeframeFilter:
    """
    Parse truncate filter specification for related tables.

    Formats:
        - table:column:start_date:end_date
        - table:start_date:end_date (assumes 'created_at' column)

    Args:
        spec: Truncate filter specification string

    Returns:
        TimeframeFilter object

    Raises:
        InvalidTimeframeError: If specification is invalid
    """
    parts = spec.split(":")

    if len(parts) == 3:
        # Format: table:start:end (assume created_at)
        table_name, start_str, end_str = parts
        column_name = "created_at"
    elif len(parts) == 4:
        # Format: table:column:start:end
        table_name, column_name, start_str, end_str = parts
    else:
        raise InvalidTimeframeError(
            f"Invalid truncate filter format: {spec}. "
            "Expected: table:column:start:end or table:start:end"
        )

    # Parse dates
    try:
        start_date = datetime.fromisoformat(start_str)
    except ValueError as e:
        raise InvalidTimeframeError(f"Invalid start date: {start_str}") from e

    try:
        end_date = datetime.fromisoformat(end_str)
    except ValueError as e:
        raise InvalidTimeframeError(f"Invalid end date: {end_str}") from e

    return TimeframeFilter(
        table_name=table_name,
        column_name=column_name,
        start_date=start_date,
        end_date=end_date,
    )


def parse_truncate_filters(specs: list[str] | None) -> list[TimeframeFilter]:
    """
    Parse multiple truncate filter specifications for related tables.

    Args:
        specs: List of truncate filter specification strings or None

    Returns:
        List of TimeframeFilter objects
    """
    if not specs:
        return []

    return [parse_truncate_filter(spec) for spec in specs]
