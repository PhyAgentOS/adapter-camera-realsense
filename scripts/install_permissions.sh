#!/usr/bin/env bash
# Install librealsense runtime tools and udev permissions.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/setup.sh" "$@"
