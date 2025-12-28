"""Tests for shared dump operations."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from pgslice.graph.models import TimeframeFilter
from pgslice.operations.dump_ops import DumpOptions, execute_dump


class TestDumpOptions:
    """Tests for DumpOptions dataclass."""

    def test_creates_with_required_fields(self) -> None:
        """Should create options with required fields."""
        options = DumpOptions(
            table="users",
            pk_values=["1", "2"],
            schema="public",
        )

        assert options.table == "users"
        assert options.pk_values == ["1", "2"]
        assert options.schema == "public"

    def test_has_correct_defaults(self) -> None:
        """Should have correct default values."""
        options = DumpOptions(
            table="users",
            pk_values=["1"],
            schema="public",
        )

        assert options.wide_mode is False
        assert options.keep_pks is False
        assert options.create_schema is False
        assert options.timeframe_filters == []
        assert options.show_progress is False

    def test_accepts_all_options(self) -> None:
        """Should accept all optional fields."""
        tf = TimeframeFilter(
            table_name="orders",
            column_name="created_at",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
        )

        options = DumpOptions(
            table="users",
            pk_values=["1"],
            schema="custom",
            wide_mode=True,
            keep_pks=True,
            create_schema=True,
            timeframe_filters=[tf],
            show_progress=True,
        )

        assert options.wide_mode is True
        assert options.keep_pks is True
        assert options.create_schema is True
        assert len(options.timeframe_filters) == 1
        assert options.show_progress is True


class TestExecuteDump:
    """Tests for execute_dump function."""

    def test_creates_dump_service_and_executes(self) -> None:
        """Should create DumpService and execute dump."""
        mock_conn_manager = MagicMock()
        mock_config = MagicMock()
        mock_result = MagicMock()

        with patch("pgslice.operations.dump_ops.DumpService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.dump.return_value = mock_result
            mock_service_class.return_value = mock_service

            options = DumpOptions(
                table="users",
                pk_values=["42"],
                schema="public",
            )

            result = execute_dump(mock_conn_manager, mock_config, options)

            # Verify DumpService was created correctly
            mock_service_class.assert_called_once_with(
                mock_conn_manager, mock_config, show_progress=False
            )

            # Verify dump was called with correct args
            mock_service.dump.assert_called_once_with(
                table="users",
                pk_values=["42"],
                schema="public",
                wide_mode=False,
                keep_pks=False,
                create_schema=False,
                timeframe_filters=[],
            )

            assert result == mock_result

    def test_passes_all_options_to_dump_service(self) -> None:
        """Should pass all options to DumpService.dump()."""
        mock_conn_manager = MagicMock()
        mock_config = MagicMock()

        tf = TimeframeFilter(
            table_name="orders",
            column_name="created_at",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 12, 31),
        )

        with patch("pgslice.operations.dump_ops.DumpService") as mock_service_class:
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service

            options = DumpOptions(
                table="users",
                pk_values=["1", "2", "3"],
                schema="custom",
                wide_mode=True,
                keep_pks=True,
                create_schema=True,
                timeframe_filters=[tf],
                show_progress=True,
            )

            execute_dump(mock_conn_manager, mock_config, options)

            # Verify show_progress is passed to constructor
            mock_service_class.assert_called_once_with(
                mock_conn_manager, mock_config, show_progress=True
            )

            # Verify all options passed to dump
            mock_service.dump.assert_called_once_with(
                table="users",
                pk_values=["1", "2", "3"],
                schema="custom",
                wide_mode=True,
                keep_pks=True,
                create_schema=True,
                timeframe_filters=[tf],
            )
