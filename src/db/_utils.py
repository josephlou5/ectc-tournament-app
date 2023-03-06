"""
Utilities for working with the database.
"""

# =============================================================================

from db.models import db

# =============================================================================


def query(model, filters=None):
    result = db.session.query(model)
    if filters is not None:
        result = result.filter_by(**filters)
    return result
