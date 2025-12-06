"""Tests for SQL writer."""

import pytest
from pathlib import Path

from snippy.dumper.writer import SQLWriter


class TestSQLWriter:
    """Tests for SQLWriter class."""

    def test_write_to_file(self, tmp_path):
        """Test writing SQL to file."""
        sql = "SELECT * FROM users;"
        output_file = tmp_path / "output.sql"

        SQLWriter.write_to_file(sql, str(output_file))

        assert output_file.exists()
        assert output_file.read_text() == sql

    def test_write_to_file_creates_directory(self, tmp_path):
        """Test writing SQL creates parent directories if they don't exist."""
        sql = "SELECT * FROM users;"
        output_file = tmp_path / "subdir" / "nested" / "output.sql"
        assert not output_file.parent.exists()

        SQLWriter.write_to_file(sql, str(output_file))

        assert output_file.exists()
        assert output_file.parent.exists()
        assert output_file.read_text() == sql

    def test_write_multiline_sql(self, tmp_path):
        """Test writing multiline SQL content."""
        sql = """BEGIN;
INSERT INTO users (id, username) VALUES (1, 'alice');
INSERT INTO users (id, username) VALUES (2, 'bob');
COMMIT;"""
        output_file = tmp_path / "output.sql"

        SQLWriter.write_to_file(sql, str(output_file))

        assert output_file.read_text() == sql

    def test_write_empty_string(self, tmp_path):
        """Test writing empty string creates empty file."""
        sql = ""
        output_file = tmp_path / "empty.sql"

        SQLWriter.write_to_file(sql, str(output_file))

        assert output_file.exists()
        assert output_file.read_text() == ""

    def test_overwrite_existing_file(self, tmp_path):
        """Test writing to existing file overwrites it."""
        output_file = tmp_path / "output.sql"
        output_file.write_text("old content")

        new_sql = "new content"
        SQLWriter.write_to_file(new_sql, str(output_file))

        assert output_file.read_text() == new_sql

    def test_write_unicode_content(self, tmp_path):
        """Test writing SQL with Unicode characters."""
        sql = "INSERT INTO users (name) VALUES ('François'), ('日本語'), ('🔥');"
        output_file = tmp_path / "unicode.sql"

        SQLWriter.write_to_file(sql, str(output_file))

        assert output_file.read_text(encoding='utf-8') == sql

    def test_write_large_content(self, tmp_path):
        """Test writing large SQL content."""
        # Generate large SQL (1000 INSERT statements)
        inserts = [f"INSERT INTO users (id) VALUES ({i});" for i in range(1000)]
        sql = "\n".join(inserts)
        output_file = tmp_path / "large.sql"

        SQLWriter.write_to_file(sql, str(output_file))

        assert output_file.exists()
        content = output_file.read_text()
        assert content == sql
        assert len(content.split("\n")) == 1000

    def test_file_path_with_spaces(self, tmp_path):
        """Test writing to file path with spaces."""
        sql = "SELECT * FROM users;"
        output_file = tmp_path / "my output file.sql"

        SQLWriter.write_to_file(sql, str(output_file))

        assert output_file.exists()
        assert output_file.read_text() == sql

    def test_absolute_path(self, tmp_path):
        """Test writing using absolute path."""
        sql = "SELECT * FROM users;"
        output_file = tmp_path / "output.sql"
        absolute_path = output_file.absolute()

        SQLWriter.write_to_file(sql, str(absolute_path))

        assert output_file.exists()
        assert output_file.read_text() == sql
