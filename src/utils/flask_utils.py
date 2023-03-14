"""
Utilities for Flask.
"""

# =============================================================================

from collections import defaultdict

from flask import get_flashed_messages

# =============================================================================

__all__ = ("get_flashed_by_categories",)

# =============================================================================


def get_flashed_by_categories(*categories, subcategories=False):
    """Returns the flashed messages in the current session, split into
    the categories of each message.

    Only the given categories will be included, or all of them if none
    are given.

    If only one category is given, the first layer of category names
    will be omitted.

    If `subcategories` is True, each category is expected to be in the
    format `category.subcategory` (with an empty subcategory if no dot
    is found). The resulting messages will then be split into category
    and subcategory. Note that only the first dot will be split.
    """
    categories = set(categories)
    all_categories = len(categories) == 0
    if not subcategories:
        flashed = defaultdict(list)
        for category, message in get_flashed_messages(with_categories=True):
            if all_categories or category in categories:
                flashed[category].append(message)
    else:
        flashed = defaultdict(lambda: defaultdict(list))
        for category, message in get_flashed_messages(with_categories=True):
            parts = category.split(".", 1)
            if len(parts) == 1:
                parent = parts[0]
                child = ""
            else:
                parent, child = parts
            if all_categories or parent in categories:
                flashed[parent][child].append(message)
    if len(categories) == 1:
        return flashed[next(iter(categories))]
    return flashed
