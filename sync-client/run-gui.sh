#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/packages/gui"

exec npm start
