#!/usr/bin/env bash
# Exit immediately if a command exits with a non-zero status
set -e

# Start the RabbitMQ worker in the background (&)
python worker.py &

# Start the FastAPI server in the foreground
exec uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1