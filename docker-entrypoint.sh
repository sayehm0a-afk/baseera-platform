#!/bin/sh
# Runs on every container start, before the CMD (gunicorn) is exec'd.
# Applying migrations here -- rather than as a separate step the operator
# must remember to run -- means a fresh deploy never serves traffic
# against a schema it doesn't match. Alembic's own advisory lock makes
# this safe if more than one instance starts concurrently; it just
# doesn't make it *fast* -- moving to a one-shot init job is the right
# call once this deploys horizontally, not before.
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Migrations complete. Starting application..."
exec "$@"
