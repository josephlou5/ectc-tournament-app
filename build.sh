#!/bin/bash
# Build command for a deployment

# Stop if any command fails
set -e

# Upgrade pip to the latest version
python -m pip install --upgrade pip

# Install the dependencies
python -m pip install pipenv wheel
# For some reason setting the flag `--verbose` doesn't work:
# Error: --verbose and --quiet are mutually exclusive! Please choose one!
pipenv install --deploy --ignore-pipfile

# Run database migrations
flask db upgrade
