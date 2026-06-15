#!/bin/bash
# Copy pvtool source into Docker build context, then build.
# pvtool lives in the notebook repo — Docker can't access files outside its context,
# so we copy it temporarily.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PVTOOL_SRC="${SCRIPT_DIR}/../jupyter_projects/Solis_API"
DEST="${SCRIPT_DIR}/backend/pvtool-src"

echo "Copying pvtool source into Docker build context..."
rm -rf "$DEST"
mkdir -p "$DEST"

# Copy only what's needed for pip install
cp -r "$PVTOOL_SRC/pvtool" "$DEST/pvtool"
cp "$PVTOOL_SRC/pyproject.toml" "$DEST/pyproject.toml"

echo "Building Docker containers..."
cd "$SCRIPT_DIR"
docker compose build

echo "Done. Run 'docker compose up' to start the app."
