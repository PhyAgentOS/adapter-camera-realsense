#!/usr/bin/env bash
# Install the reviewed udev rule and configure the invoking user's permissions.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/setup.sh" "$@"
