"""
Utilities for communicating with Mailchimp.
"""

# =============================================================================

import mailchimp_marketing as mc
from mailchimp_marketing.api_client import ApiClientError

import db

# =============================================================================

GLOBAL_CLIENT = None


def get_client(api_key=None, force=False):
    """Gets the Mailchimp client.

    If the info is not given, uses the one saved in the database.

    Returns:
        Union[Tuple[str, None], Tuple[None, mailchimp.Client]]:
            A tuple of an error message, or the Mailchimp client.
    """
    global GLOBAL_CLIENT  # pylint: disable=global-statement

    # fetch info if not given
    from_db = False
    if api_key is None:
        api_key = db.global_state.get_mailchimp_api_key()
        if api_key is None:
            return "No Mailchimp API key in database", None
        from_db = True

    # check cached client
    if not force and GLOBAL_CLIENT is not None:
        if GLOBAL_CLIENT.api_client.api_key == api_key:
            return None, GLOBAL_CLIENT

    # the documentation says that i need to provide a server, but the
    # code extracts the server from the api key anyway, so to make
    # things easier i won't require it from the user
    # https://mailchimp.com/developer/marketing/guides/quick-start/#make-your-first-api-call
    client = mc.Client({"api_key": api_key})
    if client.api_client.server in ("", "invalid-server"):
        # this case causes a "max request retries" error because the
        # host url for the request is not valid
        if from_db:
            # remove the api key from the database
            _ = db.global_state.clear_mailchimp_api_key()
        return "Invalid API key", None
    try:
        client.ping.get()
    except ApiClientError as ex:
        GLOBAL_CLIENT = None
        if from_db:
            # remove the api key from the database
            _ = db.global_state.clear_mailchimp_api_key()
        return str(ex.text), None

    GLOBAL_CLIENT = client
    return None, client
