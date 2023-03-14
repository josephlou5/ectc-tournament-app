"""
Utilities for Flask.
"""

# =============================================================================

from collections import defaultdict

from flask import get_flashed_messages

# =============================================================================

__all__ = ("get_flashed_by_categories",)

# =============================================================================


def get_flashed_by_categories():
    """Returns the flashed messages in the current session, split into
    the categories of each message.
    """
    flashed = defaultdict(list)
    for category, message in get_flashed_messages(with_categories=True):
        flashed[category].append(message)
    return flashed
