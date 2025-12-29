#!/bin/sh
set -e

# Docker entrypoint for pgslice
# Fixes permissions on mounted volumes to allow UID 1000 (pgslice user) to write

DUMPS_DIR="/home/pgslice/.pgslice/dumps"
CACHE_DIR="/home/pgslice/.cache/pgslice"

# Function to check if directory is writable
is_writable() {
    su-exec pgslice test -w "$1" 2>/dev/null
}

# Function to fix permissions if needed
fix_permissions() {
    local dir="$1"

    # Only fix if directory exists and is not writable by pgslice user
    if [ -d "$dir" ] && ! is_writable "$dir"; then
        echo "Fixing permissions on $dir..."
        # Change ownership to pgslice:pgslice (UID:GID 1000:1000)
        chown -R pgslice:pgslice "$dir" 2>/dev/null || {
            echo "Warning: Could not fix permissions on $dir. Volume may be read-only or owned by different user."
            echo "To fix: Run 'sudo chown -R 1000:1000 ./dumps' on host before mounting."
        }
    fi
}

# Fix permissions on dumps directory if mounted
if [ -d "$DUMPS_DIR" ]; then
    fix_permissions "$DUMPS_DIR"
fi

# Fix permissions on cache directory if mounted
if [ -d "$CACHE_DIR" ]; then
    fix_permissions "$CACHE_DIR"
fi

# If no command provided, show help
if [ $# -eq 0 ]; then
    exec su-exec pgslice pgslice --help
fi

# Execute command as pgslice user
exec su-exec pgslice "$@"
