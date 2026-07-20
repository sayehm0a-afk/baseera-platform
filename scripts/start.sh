#!/bin/bash

echo "Starting Basirah application..."

# Ensure Docker Compose is installed and running
if ! command -v docker-compose &> /dev/null
then
    echo "docker-compose could not be found. Please install Docker Compose."
    exit 1
fi

# Start services in detached mode
docker-compose up -d

echo "Basirah application started."
