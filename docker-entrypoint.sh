#!/bin/sh
set -e

# Docker bind-mount check: if the host file didn't exist when
# docker-compose started, Docker creates it as an empty directory.
# Detect this and give a clear error instead of a confusing Python traceback.
for f in config.yaml cookies.txt; do
    if [ -d "/app/$f" ]; then
        echo "ERROR: /app/$f is a directory — Docker created it because the file"
        echo "       didn't exist on the host when the container started."
        echo ""
        echo "  Fix: on the host, remove the directory and create the file:"
        echo "       rm -rf $f && touch $f"
        echo "  Then restart: docker compose up"
        exit 1
    fi
done

# music-porter subcommands — delegate to the Python script
case "$1" in
    server|web|pipeline|download|convert|tag|restore|reset|sync-usb|cover-art|summary)
        exec python3 /app/music-porter --no-venv "$@"
        ;;
esac

# Anything else (e.g. "bash" for debugging)
exec "$@"
