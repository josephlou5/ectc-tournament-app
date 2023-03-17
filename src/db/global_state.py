"""
Helper methods for the GlobalState table.

This table is only meant to hold one row. The first row will always be
used in any of the functions.
"""

# =============================================================================

from datetime import datetime

import pytz

from db._utils import query
from db.models import GlobalState, db

# =============================================================================

EASTERN_TZ = pytz.timezone("US/Eastern")

# =============================================================================


def get():
    """Gets the single global state, and creates it if it doesn't exist."""
    global_state = query(GlobalState).first()
    if global_state is None:
        global_state = GlobalState()
        db.session.add(global_state)
        db.session.commit()
    return global_state


def _set(global_state=None, *, commit=True, **values):
    """Sets the given kwargs values on the global state.

    Returns:
        bool: If the global state changed.
    """
    if global_state is None:
        global_state = get()
    changed = False
    for key, value in values.items():
        if getattr(global_state, key) == value:
            continue
        setattr(global_state, key, value)
        changed = True
    if commit and changed:
        db.session.commit()
    return changed


def get_service_account_info():
    """Returns the global service account info as a dict, or None if
    there is no current service account.
    """
    global_state = get()
    return global_state.service_account_info


def get_service_account_email():
    """Returns the email of the global service account, or None if there
    is no current service account.
    """
    global_state = get()
    return global_state.service_account_email


def set_service_account_info(data):
    """Sets the given info dict as the global service account.

    Returns:
        bool: Whether the operation was successful.
    """
    _set(service_account_info=data)
    return True


def clear_service_account_info():
    """Clears the global service account credentials.

    Returns:
        bool: Whether the operation was successful.
    """
    return set_service_account_info(None)


def get_tms_spreadsheet_id():
    """Returns the id of the saved global TMS spreadsheet, or None if it
    has not been saved yet.
    """
    global_state = get()
    return global_state.tms_spreadsheet_id


def set_tms_spreadsheet_id(spreadsheet_id):
    """Sets the given id as the global TMS spreadsheet id.

    Returns:
        bool: Whether the operation was successful.
    """
    _set(tms_spreadsheet_id=spreadsheet_id)
    return True


def clear_tms_spreadsheet_id():
    """Clears the global TMS spreadsheet id.

    Returns:
        bool: Whether the operation was successful.
    """
    return set_tms_spreadsheet_id(None)


def get_roster_last_fetched_time(tz=EASTERN_TZ):
    """Returns the last fetched time of the roster from the TMS
    spreadsheet, or None if the spreadsheet was not fetched yet.
    """
    global_state = get()
    return global_state.roster_last_fetched_tz(tz=tz)


def set_roster_last_fetched_time():
    """Sets the current time as the global last fetched time of the
    roster.

    Returns:
        bool: Whether the operation was successful.
    """
    _set(roster_last_fetched_time=datetime.utcnow())
    return True


def get_last_matches_query():
    """Returns the global last matches query, or None if no query was
    made yet.
    """
    global_state = get()
    return global_state.last_matches_query


def set_last_matches_query(matches_query):
    """Sets the global last matches query.

    Returns:
        bool: Whether the operation was successful.
    """
    _set(last_matches_query=matches_query)
    return True


def clear_roster_related_fields():
    """Clears the global last fetched time of the roster and the last
    matches query.

    Returns:
        bool: Whether the operation was successful.
    """
    _set(roster_last_fetched_time=None, last_matches_query=None)
    return True


def get_mailchimp_api_key():
    """Returns the Mailchimp API key, or None if it does not exist."""
    global_state = get()
    return global_state.mailchimp_api_key


def set_mailchimp_api_key(api_key):
    """Sets the Mailchimp API key.

    Returns:
        bool: Whether the operation was successful.
    """
    _set(mailchimp_api_key=api_key)
    return True


def clear_mailchimp_api_key():
    """Clears the Mailchimp API key.

    Returns:
        bool: Whether the operation was successful.
    """
    return set_mailchimp_api_key(None)
