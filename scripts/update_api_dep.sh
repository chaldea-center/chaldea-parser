#!/bin/sh
pip uninstall --yes fgo-game-data-api && poetry update fgo-game-data-api
# poetry self add poetry-plugin-export
# poetry export --without-hashes --without-urls -f requirements.txt -o requirements.txt
