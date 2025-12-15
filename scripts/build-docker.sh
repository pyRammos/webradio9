#!/bin/bash
set -e

# Build WebRadio9 Docker image
echo "Building WebRadio9 Docker image..."

# Get version from git tag or use 'latest'
VERSION=$(git describe --tags --always 2>/dev/null || echo "latest")

# Build the image
docker build -t pyrammos/webradio9:$VERSION .
docker tag pyrammos/webradio9:$VERSION pyrammos/webradio9:latest

echo "Built images:"
echo "  pyrammos/webradio9:$VERSION"
echo "  pyrammos/webradio9:latest"

# Optional: Push to Docker Hub
read -p "Push to Docker Hub? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Pushing to Docker Hub..."
    docker push pyrammos/webradio9:$VERSION
    docker push pyrammos/webradio9:latest
    echo "Images pushed successfully!"
fi
