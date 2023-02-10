#!/bin/bash
# Start command for a deployment

# Assumes `build.sh` was already run
gunicorn --chdir ./src app:app
