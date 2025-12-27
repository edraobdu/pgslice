# Use official Python Alpine image for stability
FROM python:3.13-alpine

# Copy uv binary directly from official uv image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install system dependencies
RUN apk add --no-cache postgresql-client

# Install the project into `/app`
WORKDIR /app

# Enable bytecode compilation for faster startup
ENV UV_COMPILE_BYTECODE=1
ENV UV_SYSTEM_PYTHON=1
# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Export runtime dependencies to requirements.txt and install to system Python
# This allows Docker to cache dependencies separately from source code changes
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv export --frozen --no-dev --no-emit-project --format requirements.txt --no-hashes -o requirements.txt && \
    uv pip install -r requirements.txt

# Copy the rest of the project source code
COPY . /app

# Install the project itself (production dependencies only)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-deps -e .

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Create non-root user for proper file permissions (Alpine syntax)
RUN adduser -D -u 1000 pgslice && \
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
