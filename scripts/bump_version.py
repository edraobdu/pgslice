#!/usr/bin/env python3
"""
Script to bump version in pyproject.toml following semantic versioning.

Usage:
    python bump_version.py patch  # 0.1.1 -> 0.1.2
    python bump_version.py minor  # 0.1.1 -> 0.2.0
    python bump_version.py major  # 0.1.1 -> 1.0.0
"""

import re
import sys
from pathlib import Path


def bump_version(current_version: str, bump_type: str) -> str:
    """
    Bump version according to semver rules.

    Args:
        current_version: Current version string (e.g., "0.1.1")
        bump_type: Type of bump ("major", "minor", or "patch")

    Returns:
        New version string

    Raises:
        ValueError: If version format is invalid or bump_type is unknown
    """
    # Parse version
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", current_version)
    if not match:
        raise ValueError(f"Invalid version format: {current_version}")

    major, minor, patch = map(int, match.groups())

    # Bump according to type
    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    elif bump_type == "patch":
        patch += 1
    else:
        raise ValueError(f"Unknown bump type: {bump_type}. Use major, minor, or patch")

    return f"{major}.{minor}.{patch}"


def update_pyproject_version(new_version: str, pyproject_path: Path) -> None:
    """
    Update version in pyproject.toml file.

    Args:
        new_version: New version string
        pyproject_path: Path to pyproject.toml file
    """
    content = pyproject_path.read_text()

    # Replace version line
    new_content = re.sub(
        r'^version = "[^"]*"',
        f'version = "{new_version}"',
        content,
        flags=re.MULTILINE,
    )

    if content == new_content:
        raise ValueError("Version line not found in pyproject.toml")

    pyproject_path.write_text(new_content)


def main() -> int:
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python bump_version.py [major|minor|patch]", file=sys.stderr)
        return 1

    bump_type = sys.argv[1].lower()
    if bump_type not in ("major", "minor", "patch"):
        print(
            f"Error: Invalid bump type '{bump_type}'. Use major, minor, or patch",
            file=sys.stderr,
        )
        return 1

    # Find pyproject.toml (should be in repo root)
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    pyproject_path = repo_root / "pyproject.toml"

    if not pyproject_path.exists():
        print(f"Error: pyproject.toml not found at {pyproject_path}", file=sys.stderr)
        return 1

    try:
        # Read current version
        content = pyproject_path.read_text()
        version_match = re.search(r'^version = "([^"]*)"', content, re.MULTILINE)

        if not version_match:
            print("Error: Version line not found in pyproject.toml", file=sys.stderr)
            return 1

        current_version = version_match.group(1)

        # Bump version
        new_version = bump_version(current_version, bump_type)

        # Update file
        update_pyproject_version(new_version, pyproject_path)

        print(f"{current_version} -> {new_version}")
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
