"""Integration test fixtures.

These fixtures require a real PostgreSQL database.
Set environment variables for connection:
- TEST_DB_HOST (default: localhost)
- TEST_DB_PORT (default: 5432)
- TEST_DB_NAME (default: test_pgslice)
- TEST_DB_USER (default: postgres)
- TEST_DB_PASSWORD (optional)
"""

from __future__ import annotations

import os

import pytest

# Skip all integration tests if no database is available
pytestmark = pytest.mark.integration


def pytest_configure(config: pytest.Config) -> None:
    """Register integration marker."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (require PostgreSQL)"
    )


@pytest.fixture(scope="session")
def db_host() -> str:
    """Get database host from environment."""
    return os.getenv("TEST_DB_HOST", "localhost")


@pytest.fixture(scope="session")
def db_port() -> int:
    """Get database port from environment."""
    return int(os.getenv("TEST_DB_PORT", "5432"))


@pytest.fixture(scope="session")
def db_name() -> str:
    """Get database name from environment."""
    return os.getenv("TEST_DB_NAME", "test_pgslice")


@pytest.fixture(scope="session")
def db_user() -> str:
    """Get database user from environment."""
    return os.getenv("TEST_DB_USER", "postgres")


@pytest.fixture(scope="session")
def db_password() -> str | None:
    """Get database password from environment."""
    return os.getenv("TEST_DB_PASSWORD")


@pytest.fixture(scope="session")
def postgres_connection(
    db_host: str,
    db_port: int,
    db_name: str,
    db_user: str,
    db_password: str | None,
) -> None:
    """
    Create a PostgreSQL connection for integration tests.

    This fixture is a placeholder. Implement when running integration tests.
    """
    pytest.skip("PostgreSQL connection not configured for integration tests")


@pytest.fixture
def sample_schema(postgres_connection: None) -> None:
    """
    Create sample tables with foreign key relationships.

    This fixture is a placeholder. Implement when running integration tests.
    Tables to create:
    - users (id, name, manager_id -> users)
    - organizations (id, name)
    - orders (id, user_id -> users, created_at)
    - order_items (id, order_id -> orders, product_id -> products)
    - products (id, name, category_id -> categories)
    - categories (id, name)
    """
    pass
