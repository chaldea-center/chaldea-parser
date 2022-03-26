#!/bin/sh
pip uninstall --yes fgo-game-data-api && poetry update fgo-game-data-api
poetry export --without-hashes -f requirements.txt -o requirements.txt
