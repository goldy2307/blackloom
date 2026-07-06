#!/bin/sh
# Runs as root on container start (required to fix ownership), then drops
# to the unprivileged appuser before actually running the server.
#
# Why this exists: Docker's VOLUME instruction, and Render's persistent disks,
# both default new mount points to root-owned. appuser can't write to those
# until something with root permissions chowns them — that has to happen on
# every container start, not just at build time, because Render's disk content
# persists across deploys and each fresh mount can come back root-owned.
set -e

mkdir -p /app/data /app/logs
chown -R appuser:appuser /app/data /app/logs

exec su -s /bin/sh -c "cd /app/api && exec uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1" appuser
