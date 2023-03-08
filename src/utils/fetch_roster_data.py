"""
Fetches the full team roster from the given spreadsheet link.
"""

# =============================================================================

import google.auth.exceptions
import gspread

# =============================================================================

GLOBAL_SERVICE_ACCOUNT = None


def get_service_account_client(service_account_info):
    """Gets the service account using the given info.

    Returns:
        Union[Tuple[str, None], Tuple[None, gspread.Client]]:
            A tuple of an error message, or the service account client.
    """
    global GLOBAL_SERVICE_ACCOUNT  # pylint: disable=global-statement
    # check cached service account client
    if GLOBAL_SERVICE_ACCOUNT is not None:
        email = service_account_info["client_email"]
        if email == GLOBAL_SERVICE_ACCOUNT.auth.service_account_email:
            # assume same service account
            return None, GLOBAL_SERVICE_ACCOUNT
    try:
        client = gspread.service_account_from_dict(
            service_account_info, scopes=gspread.auth.READONLY_SCOPES
        )
    except google.auth.exceptions.MalformedError as ex:
        GLOBAL_SERVICE_ACCOUNT = None
        return str(ex), None
    GLOBAL_SERVICE_ACCOUNT = client
    return None, client


def fetch(url):
    """Fetches the full team roster from the given spreadsheet link.

    No validation is done beyond required and optional columns.
    """
    # TODO
