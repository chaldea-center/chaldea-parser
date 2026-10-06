#!/usr/bin/env bash
set -e

poetry run ruff format --check src scripts main.py
poetry run ruff check src scripts main.py
poetry run basedpyright