# Multi-stage build with uv and Python 3.13
# Note: Update to python3.14 when official Docker images are available
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

WORKDIR /app

# Copy dependency files (including lockfile for reproducible builds)
COPY pyproject.toml uv.lock README.md ./

# Copy application source
COPY src/ ./src/

# Create virtual environment and install dependencies using lockfile
# --frozen ensures exact versions from uv.lock are used
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN uv sync --frozen

# Runtime stage
FROM python:3.13-slim

# Install runtime system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application
COPY --from=builder /app /app
WORKDIR /app

# Activate virtual environment
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Create cache directory
RUN mkdir -p /root/.cache/snippy

# Default command
CMD ["snippy", "--help"]
