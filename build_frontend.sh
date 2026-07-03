#!/bin/bash
set -e

# Build the AIOS React frontend and copy it into the backend static path.

NODE_BIN="${HOME}/.local/node/bin"
if [ -d "$NODE_BIN" ]; then
    export PATH="$NODE_BIN:$PATH"
fi

if ! command -v npm &> /dev/null; then
    echo "npm not found. Install Node.js first."
    exit 1
fi

FRONTEND_DIR="/Users/hassanka/Dev/AIOS-Front"
BACKEND_APP_DIR="/Users/hassanka/Downloads/AIOS/app"

cd "$FRONTEND_DIR"
npm install
npm run build

rm -rf "$BACKEND_APP_DIR"
cp -R "$FRONTEND_DIR/dist" "$BACKEND_APP_DIR"

echo "Frontend built and copied to $BACKEND_APP_DIR"
