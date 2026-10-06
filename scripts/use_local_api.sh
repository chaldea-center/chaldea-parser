#!/usr/bin/env bash
# Overlay the venv copy of fgo-game-data-api with the local sibling checkout
# at ../fgo-game-data-api-c (editable install), so uncommitted local changes
# take effect without relocking.
#
# NOTE: `poetry install` reinstalls the locked git build and clobbers this
# overlay, so re-run this script afterwards.
#
# Restore the locked (git-built) copy:
#   poetry run pip uninstall -y fgo-game-data-api && poetry install
set -e

cd "$(dirname "$0")/.."
poetry run pip install --no-deps --editable ../fgo-game-data-api-c