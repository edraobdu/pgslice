"""Tests for pgslice.dumper.writer module."""

from __future__ import annotations

from pathlib import Path

from freezegun import freeze_time

from pgslice.dumper.writer import SQLWriter


class TestSQLWriter:
    """Tests for SQLWriter class."""


class TestWriteToFile(TestSQLWriter):
    """Tests for write_to_file method."""

    def test_write_simple_content(self, tmp_path: Path) -> None:
        """Should write content to file."""
        output_path = tmp_path / "test.sql"
        content = "SELECT 1;"

        SQLWriter.write_to_file(content, output_path)

        assert output_path.exists()
        assert output_path.read_text() == content

    def test_write_multiline_content(self, tmp_path: Path) -> None:
        """Should write multiline content correctly."""
        output_path = tmp_path / "test.sql"
        content = "BEGIN;\nINSERT INTO users VALUES (1);\nCOMMIT;"

        SQLWriter.write_to_file(content, output_path)

        assert output_path.read_text() == content

    def test_write_unicode_content(self, tmp_path: Path) -> None:
        """Should handle unicode content correctly."""
        output_path = tmp_path / "test.sql"
        content = "INSERT INTO users (name) VALUES ('日本語テスト');"

        SQLWriter.write_to_file(content, output_path)

        assert output_path.read_text(encoding="utf-8") == content

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        """Should create parent directories if they don't exist."""
        output_path = tmp_path / "nested" / "deep" / "test.sql"
        content = "SELECT 1;"

        SQLWriter.write_to_file(content, output_path)

        assert output_path.exists()
        assert output_path.read_text() == content

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        """Should overwrite existing file."""
        output_path = tmp_path / "test.sql"

        # Write initial content
        output_path.write_text("OLD CONTENT")

        # Overwrite
        new_content = "NEW CONTENT"
        SQLWriter.write_to_file(new_content, output_path)

        assert output_path.read_text() == new_content

    def test_accepts_string_path(self, tmp_path: Path) -> None:
        """Should accept string path as well as Path object."""
        output_path_str = str(tmp_path / "test.sql")
        content = "SELECT 1;"

        SQLWriter.write_to_file(content, output_path_str)

        assert Path(output_path_str).read_text() == content


class TestGenerateDefaultFilename(TestSQLWriter):
    """Tests for generate_default_filename method."""

    @freeze_time("2024-03-15 14:30:52")
    def test_basic_filename(self) -> None:
        """Should generate filename with table, pk, and timestamp."""
        filename = SQLWriter.generate_default_filename("users", "42")
        assert filename == "users_42_20240315_143052.sql"

    @freeze_time("2024-01-01 00:00:00")
    def test_new_year_timestamp(self) -> None:
        """Should handle new year timestamp correctly."""
        filename = SQLWriter.generate_default_filename("orders", "1")
        assert filename == "orders_1_20240101_000000.sql"

    def test_custom_schema(self) -> None:
        """Should include schema in filename if not public."""
        filename = SQLWriter.generate_default_filename("users", "42", schema="custom")
        assert filename.startswith("custom_users_42_")
        assert filename.endswith(".sql")

    def test_public_schema_not_included(self) -> None:
        """Should not include 'public' schema in filename."""
        filename = SQLWriter.generate_default_filename("users", "42", schema="public")
        assert not filename.startswith("public_")
        assert filename.startswith("users_42_")

    def test_empty_schema_treated_as_public(self) -> None:
        """Empty schema should be treated as public."""
        filename = SQLWriter.generate_default_filename("users", "42", schema="")
        assert not filename.startswith("_")
        assert filename.startswith("users_42_")

    def test_sanitizes_pk_with_slashes(self) -> None:
        """Should sanitize PK values containing slashes."""
        filename = SQLWriter.generate_default_filename("files", "path/to/file")
        assert "/" not in filename
        assert "path_to_file" in filename

    def test_sanitizes_pk_with_backslashes(self) -> None:
        """Should sanitize PK values containing backslashes."""
        filename = SQLWriter.generate_default_filename("files", "path\\to\\file")
        assert "\\" not in filename
        assert "path_to_file" in filename

    def test_sanitizes_pk_with_spaces(self) -> None:
        """Should sanitize PK values containing spaces."""
        filename = SQLWriter.generate_default_filename("documents", "my document")
        assert " " not in filename
        assert "my_document" in filename

    def test_composite_pk_value(self) -> None:
        """Should handle composite PK values as string."""
        filename = SQLWriter.generate_default_filename("order_items", "1,2")
        assert "1,2" in filename or "1_2" in filename


class TestGetDefaultOutputPath(TestSQLWriter):
    """Tests for get_default_output_path method."""

    def test_creates_output_directory(self, tmp_path: Path) -> None:
        """Should create output directory if it doesn't exist."""
        output_dir = tmp_path / "new_output_dir"
        assert not output_dir.exists()

        SQLWriter.get_default_output_path(output_dir, "users", "42")

        assert output_dir.exists()

    @freeze_time("2024-06-20 10:15:30")
    def test_returns_full_path(self, tmp_path: Path) -> None:
        """Should return full path with generated filename."""
        output_dir = tmp_path / "dumps"

        path = SQLWriter.get_default_output_path(output_dir, "users", "42")

        assert path.parent == output_dir
        assert path.name == "users_42_20240620_101530.sql"

    def test_with_custom_schema(self, tmp_path: Path) -> None:
        """Should include schema in filename."""
        output_dir = tmp_path / "dumps"

        path = SQLWriter.get_default_output_path(
            output_dir, "users", "42", schema="admin"
        )

        assert "admin_users_42_" in path.name


class TestWriteToStdout(TestSQLWriter):
    """Tests for write_to_stdout method."""

    def test_does_not_raise(self) -> None:
        """Should not raise when called with valid content."""
        # write_to_stdout just logs, doesn't actually print
        # so we just verify it doesn't raise
        SQLWriter.write_to_stdout("SELECT 1;")

    def test_handles_empty_content(self) -> None:
        """Should handle empty content."""
        SQLWriter.write_to_stdout("")

    def test_handles_unicode(self) -> None:
        """Should handle unicode content."""
        SQLWriter.write_to_stdout("INSERT INTO t VALUES ('日本語');")
