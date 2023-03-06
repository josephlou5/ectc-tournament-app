"""
Fetches the full team roster from the given spreadsheet link.
"""

# =============================================================================

import google.auth.exceptions
import gspread

# =============================================================================


def get_service_account(service_account_info):
    """Gets the service account using the given info.

    Returns:
        Union[Tuple[str, None], Tuple[None, gspread.Client]]:
            A tuple of an error message, or the service account client.
    """
    try:
        client = gspread.service_account_from_dict(
            service_account_info, scopes=gspread.auth.READONLY_SCOPES
        )
    except google.auth.exceptions.MalformedError as ex:
        return str(ex), None
    return None, client


def fetch(url):
    """Fetches the full team roster from the given spreadsheet link.

    No validation is done beyond required and optional columns.
    """
    # TODO
