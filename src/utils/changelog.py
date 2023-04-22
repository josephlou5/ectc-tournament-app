"""
Utilities for the changelog file.
"""

# =============================================================================

import json

import utils

# =============================================================================

CHANGELOG_FILE = utils.STATIC_FOLDER / "changelog.json"

TIMESTAMP_FMT = "%Y-%m-%d %H:%M"

# =============================================================================


def _read():
    if not CHANGELOG_FILE.exists():
        return []
    changes = json.loads(CHANGELOG_FILE.read_bytes())
    for change in changes:
        version_parts = change["version"].split(".")
        change["version_tuple"] = tuple(map(int, version_parts))
    return sorted(changes, key=lambda c: c["version_tuple"], reverse=True)


def read_changelog():
    return _read()


def get_latest_version():
    changes = _read()
    if len(changes) == 0:
        return ""
    latest_version = changes[0]["version"]
    return f"v{latest_version}"
