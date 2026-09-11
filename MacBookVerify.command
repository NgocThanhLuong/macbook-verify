#!/bin/bash
set -u
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec /bin/bash "$ROOT_DIR/scripts/verify.sh" "$@"
