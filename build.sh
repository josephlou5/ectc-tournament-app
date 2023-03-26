#!/bin/bash
# Build command for a deployment

# Upgrade pip to the latest version
python -m pip install --upgrade pip

# Install the dependencies
python -m pip install pipenv wheel
pipenv install --deploy --ignore-pipfile --verbose

# Run database migrations
flask db upgrade
