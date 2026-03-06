#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "Installing dependencies..."
npm install

echo ""
echo "Building all packages..."
npm run build

echo ""
echo "Done! You can now run:"
echo "  ./run-gui.sh        — Launch the Electron app"
echo "  ./run-cli.sh        — Launch the CLI (interactive mode)"
echo "  ./run-cli.sh --help — Show CLI commands"
