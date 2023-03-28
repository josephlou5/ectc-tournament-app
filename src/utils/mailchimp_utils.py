"""
Utilities for communicating with Mailchimp.
"""

# =============================================================================

from datetime import datetime

import mailchimp_marketing as mc
from mailchimp_marketing.api_client import ApiClientError

import db
import utils

# =============================================================================

PAGINATION_LIMIT = 100

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


def clear_global_client():
    """Clears the global Mailchimp client."""
    global GLOBAL_CLIENT  # pylint: disable=global-statement
    GLOBAL_CLIENT = None


# =============================================================================

# Helpers for API calls


def _get_fields_list(fields, prefix=None, include_total=True):
    """Converts my own specification of fields to include into a single
    list of fields, in accordance with the Mailchimp API.
    """
    fields_list = set()

    def add(field):
        if prefix is not None:
            field = f"{prefix}.{field}"
        fields_list.add(field)

    for field_path in fields.values():
        if isinstance(field_path, str):
            add(field_path)
        else:
            # assume it is an iterable of path segments
            add(".".join(field_path))
    if include_total:
        fields_list.add("total_items")
    return list(fields_list)


def _get_key_path_value(obj, path):
    if isinstance(path, str):
        return obj[path]
    # assume it is an iterable of path segments
    for key in path:
        obj = obj[key]
    return obj


def _extract_fields(fields, obj):
    extracted = {}
    for key, path in fields.items():
        value = _get_key_path_value(obj, path)
        if value == "":
            value = None
        extracted[key] = value
    return extracted


# =============================================================================

AUDIENCE_FIELDS = {
    "id": "id",
    "name": "name",
    "from_name": ("campaign_defaults", "from_name"),
    "from_email": ("campaign_defaults", "from_email"),
    "subject": ("campaign_defaults", "subject"),
    "num_members": ("stats", "member_count"),
    "last_sent": ("stats", "campaign_last_sent"),
}


def get_audiences():
    """Gets the Mailchimp audiences.

    Returns:
        Union[Tuple[str, None], Tuple[None, List[Dict]]]:
            A tuple of an error messages, or a list of audience infos in
            the format:
                'id': audience id
                'name': audience name
                'from_name': the default from name
                'from_email': the default from email
                'subject': the default subject
                'num_members': the number of members
                'last_sent': the time of the last sent campaign
    """

    error_msg, client = get_client()
    if error_msg is not None:
        return error_msg, None

    audiences = []
    total_items = None
    seen_items = 0

    while True:
        # https://mailchimp.com/developer/marketing/api/lists/get-lists-info/
        response = client.lists.get_all_lists(
            fields=_get_fields_list(AUDIENCE_FIELDS, prefix="lists"),
            count=PAGINATION_LIMIT,
            offset=seen_items,
        )
        if total_items is None:
            total_items = response["total_items"]
        paginated = response["lists"]

        for audience in paginated:
            audience_info = _extract_fields(AUDIENCE_FIELDS, audience)
            # convert "last_sent" to str in eastern time
            if audience_info["last_sent"] is not None:
                audience_info["last_sent"] = utils.dt_str(
                    datetime.fromisoformat(audience_info["last_sent"])
                )
            audiences.append(audience_info)

        seen_items += len(paginated)
        if seen_items >= total_items:
            break

    return None, audiences


def get_audience(audience_id):
    """Gets the requested audience, or None if it doesn't exist.

    Returns:
        Union[Tuple[str, None], Tuple[None, Dict]]:
            An error messages, or the audience info in the format:
                'id': audience id
                'name': audience name
                'from_name': the default from name
                'from_email': the default from email
                'subject': the default subject
                'num_members': the number of members
                'last_sent': the time of the last sent campaign
    """

    error_msg, client = get_client()
    if error_msg is not None:
        return error_msg, None

    try:
        response = client.lists.get_list(
            audience_id, fields=_get_fields_list(AUDIENCE_FIELDS)
        )
    except ApiClientError as ex:
        # error is: {
        #     "type": "https://mailchimp.com/developer/marketing/docs/errors/",
        #     "title": "Resource Not Found",
        #     "status": 404,
        #     "detail": "The requested resource could not be found.",
        #     "instance": "d3c1215f-555f-c179-24fb-d348b43a73b0",
        # }
        # don't have any other audience ids to test what happens if the
        # client doesn't have permission, so just assuming that an error
        # always means the audience id is invalid *for this api key*
        return ex.text, None
    return None, _extract_fields(AUDIENCE_FIELDS, response)
