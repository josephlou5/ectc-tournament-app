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


# =============================================================================


def _set(obj, *, commit=True, **values):
    """Sets the given kwargs values on the given object.

    Returns:
        bool: If any values in the object changed.
    """
    changed = False
    for key, value in values.items():
        if getattr(obj, key) == value:
            continue
        setattr(obj, key, value)
        changed = True
    if commit and changed:
        db.session.commit()
    return changed
