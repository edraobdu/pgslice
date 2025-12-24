# Use a Python image with uv pre-installed
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install the project into `/app`
WORKDIR /app

# Enable bytecode compilation for faster startup
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Install dependencies first (without the project) for better layer caching
# This allows Docker to cache dependencies separately from source code changes
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project

# Copy the rest of the project source code
COPY . /app

# Install the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

# Place executables in the environment at the front of the path
# This makes the venv "active" without manual activation
ENV PATH="/app/.venv/bin:$PATH"

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Create non-root user for proper file permissions
RUN useradd -m -u 1000 pgslice && \
    mkdir -p /home/pgslice/.cache/pgslice /home/pgslice/.pgslice/dumps && \
    chown -R pgslice:pgslice /app /home/pgslice

# Switch to non-root user
USER pgslice

# Update cache directory to use pgslice's home
ENV PGSLICE_CACHE_DIR=/home/pgslice/.cache/pgslice

# Reset the entrypoint, don't invoke `uv`
ENTRYPOINT []

# Default command
CMD ["pgslice", "--help"]
