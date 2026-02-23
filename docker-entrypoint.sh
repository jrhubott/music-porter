#!/bin/sh
set -e

# music-porter subcommands — delegate to the Python script
case "$1" in
    server|web|pipeline|download|convert|tag|restore|reset|sync-usb|cover-art|summary)
        exec python3 /app/music-porter "$@"
        ;;
esac

# Anything else (e.g. "bash" for debugging)
exec "$@"
