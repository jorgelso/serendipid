#!/bin/bash

# Serendipid Docker Stop Script

echo "🛑 Stopping Serendipid..."

# Use docker compose if available, otherwise docker-compose
if command -v docker compose &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

$DOCKER_COMPOSE down

echo "✅ Serendipid stopped."
