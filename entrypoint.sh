#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate

# Execute the passed command
echo "Starting server..."
exec "$@"
