#!/bin/bash

echo "Stopping Basirah application..."

# Ensure Docker Compose is installed
if ! command -v docker-compose &> /dev/null
then
    echo "docker-compose could not be found. Please install Docker Compose."
    exit 1
fi

# Stop and remove containers, networks, and volumes
docker-compose down

echo "Basirah application stopped."
