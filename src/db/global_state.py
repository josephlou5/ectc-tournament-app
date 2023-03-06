"""
Helper methods for the GlobalState table.

This table is only meant to hold one row. The first row will always be
used in any of the functions.
"""

# =============================================================================

import json

from db._utils import query
from db.models import GlobalState, db

# =============================================================================


def _get():
    """Gets the single global state, and creates it if it doesn't exist."""
    global_state = query(GlobalState).first()
    if global_state is None:
        global_state = GlobalState()
        db.session.add(global_state)
        db.session.commit()
    return global_state


def get_service_account_info():
    """Returns the global service account info as a dict, or None if
    there is no current service account.
    """
    global_state = _get()
    service_account_info_str = global_state.service_account
    if service_account_info_str is None:
        return None
    return json.loads(service_account_info_str)


def get_service_account_email():
    """Returns the email of the global service account, or None if there
    is no current service account.
    """
    service_account_info = get_service_account_info()
    if service_account_info is None:
        return None
    return service_account_info["client_email"]


def set_service_account_info(data):
    """Sets the given info dict as the global service account.

    Returns:
        bool: Whether the operation was successful.
    """
    global_state = _get()
    # use the most compact representation
    global_state.service_account = json.dumps(data, separators=(",", ":"))
    db.session.commit()
    return True
