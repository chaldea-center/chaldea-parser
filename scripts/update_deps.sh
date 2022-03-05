#!/bin/sh
poetry update
poetry export --without-hashes -f requirements.txt -o requirements.txt
