"""Tests for shared parsing operations."""

from __future__ import annotations

from datetime import datetime

import pytest

from pgslice.operations.parsing import parse_truncate_filter, parse_truncate_filters
from pgslice.utils.exceptions import InvalidTimeframeError


class TestParseTruncateFilter:
    """Tests for parse_truncate_filter function."""

    def test_parses_four_part_format(self) -> None:
        """Should parse table:column:start:end format."""
        result = parse_truncate_filter("orders:created_at:2024-01-01:2024-12-31")

        assert result.table_name == "orders"
        assert result.column_name == "created_at"
        assert result.start_date == datetime(2024, 1, 1)
        assert result.end_date == datetime(2024, 12, 31)

    def test_parses_three_part_format(self) -> None:
        """Should parse table:start:end format with default column."""
        result = parse_truncate_filter("orders:2024-01-01:2024-12-31")

        assert result.table_name == "orders"
        assert result.column_name == "created_at"  # Default
        assert result.start_date == datetime(2024, 1, 1)
        assert result.end_date == datetime(2024, 12, 31)

    def test_raises_for_invalid_format(self) -> None:
        """Should raise for invalid format."""
        with pytest.raises(InvalidTimeframeError) as exc_info:
            parse_truncate_filter("invalid")

        assert "Invalid truncate filter format" in str(exc_info.value)

    def test_raises_for_too_many_parts(self) -> None:
        """Should raise for too many parts."""
        with pytest.raises(InvalidTimeframeError) as exc_info:
            parse_truncate_filter("a:b:c:d:e")

        assert "Invalid truncate filter format" in str(exc_info.value)

    def test_raises_for_invalid_start_date(self) -> None:
        """Should raise for invalid start date."""
        with pytest.raises(InvalidTimeframeError) as exc_info:
            parse_truncate_filter("orders:not-a-date:2024-12-31")

        assert "Invalid start date" in str(exc_info.value)

    def test_raises_for_invalid_end_date(self) -> None:
        """Should raise for invalid end date."""
        with pytest.raises(InvalidTimeframeError) as exc_info:
            parse_truncate_filter("orders:2024-01-01:not-a-date")

        assert "Invalid end date" in str(exc_info.value)


class TestParseTruncateFilters:
    """Tests for parse_truncate_filters function."""

    def test_returns_empty_for_none(self) -> None:
        """Should return empty list for None."""
        result = parse_truncate_filters(None)
        assert result == []

    def test_returns_empty_for_empty_list(self) -> None:
        """Should return empty list for empty list."""
        result = parse_truncate_filters([])
        assert result == []

    def test_parses_single_filter(self) -> None:
        """Should parse single filter."""
        result = parse_truncate_filters(["orders:2024-01-01:2024-12-31"])

        assert len(result) == 1
        assert result[0].table_name == "orders"

    def test_parses_multiple_filters(self) -> None:
        """Should parse multiple filters."""
        result = parse_truncate_filters(
            [
                "orders:2024-01-01:2024-12-31",
                "payments:paid_at:2024-06-01:2024-06-30",
            ]
        )

        assert len(result) == 2
        assert result[0].table_name == "orders"
        assert result[1].table_name == "payments"
        assert result[1].column_name == "paid_at"

    def test_raises_for_invalid_filter_in_list(self) -> None:
        """Should raise if any filter is invalid."""
        with pytest.raises(InvalidTimeframeError):
            parse_truncate_filters(["orders:2024-01-01:2024-12-31", "invalid"])
