"""Tests for pgslice.cli module."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pgslice.cli import main


class TestMain:
    """Tests for main function."""

    def test_version_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print version and exit."""
        with patch.object(sys, "argv", ["pgslice", "--version"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "pgslice" in captured.out

    def test_help_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Should print help and exit."""
        with patch.object(sys, "argv", ["pgslice", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "PostgreSQL" in captured.out
        assert "--host" in captured.out

    def test_missing_required_params(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should fail with missing required parameters."""
        # Clear env vars
        monkeypatch.delenv("DB_HOST", raising=False)
        monkeypatch.delenv("DB_USER", raising=False)
        monkeypatch.delenv("DB_NAME", raising=False)

        with (
            patch.object(sys, "argv", ["pgslice"]),
            patch("pgslice.cli.load_config") as mock_load,
        ):
            mock_config = MagicMock()
            mock_config.db.host = ""
            mock_config.db.user = ""
            mock_config.db.database = ""
            mock_load.return_value = mock_config

            exit_code = main()
            assert exit_code == 1

    def test_clear_cache_flag(self, tmp_path: Path) -> None:
        """Should clear cache and exit."""
        with (
            patch.object(sys, "argv", ["pgslice", "--clear-cache"]),
            patch("pgslice.cli.load_config") as mock_load,
            patch("pgslice.cache.schema_cache.SchemaCache"),
        ):
            mock_config = MagicMock()
            mock_config.cache.enabled = True
            mock_config.cache.cache_dir = tmp_path
            mock_config.cache.ttl_hours = 24
            mock_load.return_value = mock_config

            exit_code = main()
            assert exit_code == 0

    def test_no_cache_flag(self) -> None:
        """Should disable caching when --no-cache is used."""
        with (
            patch.object(sys, "argv", ["pgslice", "--no-cache", "--host", "localhost"]),
            patch("pgslice.cli.load_config") as mock_load,
        ):
            mock_config = MagicMock()
            mock_config.db.host = ""
            mock_config.db.user = ""
            mock_config.db.database = ""
            mock_config.cache.enabled = True
            mock_load.return_value = mock_config

            main()

            # Cache should be disabled
            assert mock_config.cache.enabled is False

    def test_cli_args_override_config(self) -> None:
        """CLI arguments should override config values."""
        with (
            patch.object(
                sys,
                "argv",
                [
                    "pgslice",
                    "--host",
                    "cli-host",
                    "--port",
                    "5433",
                    "--user",
                    "cli-user",
                    "--database",
                    "cli-db",
                ],
            ),
            patch("pgslice.cli.load_config") as mock_load,
        ):
            mock_config = MagicMock()
            mock_config.db.host = "config-host"
            mock_config.db.port = 5432
            mock_config.db.user = "config-user"
            mock_config.db.database = "config-db"
            mock_config.db.schema = "public"
            mock_config.cache.enabled = True
            mock_config.connection_ttl_minutes = 30
            mock_load.return_value = mock_config

            with (
                patch("pgslice.cli.SecureCredentials"),
                patch("pgslice.cli.ConnectionManager") as mock_cm,
                patch("pgslice.cli.REPL"),
            ):
                mock_cm_instance = MagicMock()
                mock_cm.return_value = mock_cm_instance

                main()

            # CLI args should have overridden config
            assert mock_config.db.host == "cli-host"
            assert mock_config.db.port == 5433
            assert mock_config.db.user == "cli-user"
            assert mock_config.db.database == "cli-db"

    def test_keyboard_interrupt_handling(self) -> None:
        """Should handle keyboard interrupt gracefully."""
        with (
            patch.object(sys, "argv", ["pgslice"]),
            patch("pgslice.cli.load_config", side_effect=KeyboardInterrupt),
        ):
            exit_code = main()
            assert exit_code == 130

    def test_db_error_handling(self) -> None:
        """Should handle database errors."""
        from pgslice.utils.exceptions import DBConnectionError

        with (
            patch.object(sys, "argv", ["pgslice"]),
            patch(
                "pgslice.cli.load_config",
                side_effect=DBConnectionError("Connection failed"),
            ),
        ):
            exit_code = main()
            assert exit_code == 1

    def test_unexpected_error_handling(self) -> None:
        """Should handle unexpected errors."""
        with (
            patch.object(sys, "argv", ["pgslice"]),
            patch("pgslice.cli.load_config", side_effect=RuntimeError("Unexpected")),
        ):
            exit_code = main()
            assert exit_code == 1

    def test_log_level_argument(self) -> None:
        """Should respect log level argument."""
        with (
            patch.object(
                sys, "argv", ["pgslice", "--log-level", "DEBUG", "--clear-cache"]
            ),
            patch("pgslice.cli.setup_logging") as mock_setup,
        ):
            with patch("pgslice.cli.load_config") as mock_load:
                mock_config = MagicMock()
                mock_config.cache.enabled = False
                mock_load.return_value = mock_config

                main()

            mock_setup.assert_called_with("DEBUG")

    def test_connection_test_failure(self) -> None:
        """Should fail if connection test fails."""
        with (
            patch.object(
                sys,
                "argv",
                [
                    "pgslice",
                    "--host",
                    "localhost",
                    "--user",
                    "test",
                    "--database",
                    "test",
                ],
            ),
            patch("pgslice.cli.load_config") as mock_load,
        ):
            mock_config = MagicMock()
            mock_config.db.host = "localhost"
            mock_config.db.user = "test"
            mock_config.db.database = "test"
            mock_config.db.port = 5432
            mock_config.db.schema = "public"
            mock_config.cache.enabled = False
            mock_config.connection_ttl_minutes = 30
            mock_load.return_value = mock_config

            with (
                patch("pgslice.cli.SecureCredentials"),
                patch("pgslice.cli.ConnectionManager") as mock_cm,
            ):
                mock_cm_instance = MagicMock()
                mock_cm_instance.get_connection.side_effect = Exception(
                    "Connection failed"
                )
                mock_cm.return_value = mock_cm_instance

                exit_code = main()
                assert exit_code == 1

    def test_successful_repl_start(self) -> None:
        """Should start REPL successfully."""
        with (
            patch.object(
                sys,
                "argv",
                [
                    "pgslice",
                    "--host",
                    "localhost",
                    "--user",
                    "test",
                    "--database",
                    "test",
                ],
            ),
            patch("pgslice.cli.load_config") as mock_load,
        ):
            mock_config = MagicMock()
            mock_config.db.host = "localhost"
            mock_config.db.user = "test"
            mock_config.db.database = "test"
            mock_config.db.port = 5432
            mock_config.db.schema = "public"
            mock_config.cache.enabled = False
            mock_config.connection_ttl_minutes = 30
            mock_load.return_value = mock_config

            with patch("pgslice.cli.SecureCredentials") as mock_creds:
                mock_creds_instance = MagicMock()
                mock_creds.return_value = mock_creds_instance

                with patch("pgslice.cli.ConnectionManager") as mock_cm:
                    mock_cm_instance = MagicMock()
                    mock_cm.return_value = mock_cm_instance

                    with patch("pgslice.cli.REPL") as mock_repl:
                        mock_repl_instance = MagicMock()
                        mock_repl.return_value = mock_repl_instance

                        exit_code = main()

                        mock_repl_instance.start.assert_called_once()
                        mock_cm_instance.close.assert_called_once()
                        mock_creds_instance.clear.assert_called_once()
                        assert exit_code == 0
