"""
Utilities for communicating with Mailchimp.
"""

# =============================================================================

import hashlib
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
            # if the api key is invalid, also need to clear others
            _ = db.global_state.clear_mailchimp_related_fields()
        return "Invalid API key", None
    try:
        client.ping.get()
    except ApiClientError as ex:
        GLOBAL_CLIENT = None
        if from_db:
            # remove the api key from the database
            # if the api key is invalid, also need to clear others
            _ = db.global_state.clear_mailchimp_related_fields()
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

    for field_info in fields.values():
        field_path = field_info["path"]
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
    for key, field_info in fields.items():
        value = _get_key_path_value(obj, field_info["path"])
        if value == "":
            value = None
        elif field_info.get("is_datetime", False):
            value = utils.dt_str(
                utils.dt_to_timezone(datetime.fromisoformat(value))
            )
        extracted[key] = value
    return extracted


def _get_paginated_data(api_call, fields, data_key, additional_kwargs=None):
    all_data = []
    total_items = None
    seen_items = 0

    if additional_kwargs is None:
        kwargs = {}
    else:
        kwargs = additional_kwargs
    kwargs.update(
        {
            "fields": _get_fields_list(fields, prefix=data_key),
            "count": PAGINATION_LIMIT,
        }
    )

    while True:
        try:
            response = api_call(**kwargs, offset=seen_items)
        except ApiClientError as ex:
            error_msg = str(ex.text)
            print("Mailchimp API error:", error_msg)
            return error_msg, None
        if total_items is None:
            total_items = response["total_items"]
        paginated = response[data_key]

        for data in paginated:
            all_data.append(_extract_fields(fields, data))

        seen_items += len(paginated)
        if seen_items >= total_items:
            break

    return None, all_data


def _get_resource(api_call, resource_id, fields):
    try:
        response = api_call(resource_id, fields=_get_fields_list(fields))
    except ApiClientError as ex:
        # error is: {
        #   "type": "https://mailchimp.com/developer/marketing/docs/errors/",
        #   "title": "Resource Not Found",
        #   "status": 404,
        #   "detail": "The requested resource could not be found.",
        #   "instance": "some identifier",
        # }
        return ex.text, None
    return None, _extract_fields(fields, response)


def _get_subscriber_hash(email):
    """Returns the MD5 hash of the lowercase version of the given email,
    as used in the Mailchimp API.
    """
    return hashlib.md5(email.lower().encode()).hexdigest()


# =============================================================================

AUDIENCE_FIELDS = {
    "id": {"path": "id"},
    "name": {"path": "name"},
    "from_name": {"path": ("campaign_defaults", "from_name")},
    "from_email": {"path": ("campaign_defaults", "from_email")},
    "subject": {"path": ("campaign_defaults", "subject")},
    "num_members": {"path": ("stats", "member_count")},
    "last_sent": {
        "path": ("stats", "campaign_last_sent"),
        "is_datetime": True,
    },
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
    return _get_paginated_data(
        client.lists.get_all_lists, AUDIENCE_FIELDS, "lists"
    )


def get_audience(audience_id):
    """Gets the requested audience.

    Returns:
        Union[Tuple[str, None], Tuple[None, Dict]]:
            An error message, or the audience info in the format:
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
    return _get_resource(client.lists.get_list, audience_id, AUDIENCE_FIELDS)


# =============================================================================


def add_members(audience_id, emails, tournament_tag=None, remove_emails=None):
    """Adds the given member emails to the given audience with the
    optional given tournament tag.

    If `remove_emails` is given, the given tournament tag will be
    removed from those emails.

    An error will be returned upon the first invalid request (except for
    invalid emails), but all previous requests will have gone through.
    Multiple calls to this function will not have any ill effects (the
    members list will only be updated with these emails), so it is safe
    to retry the function call if there is any error.

    Returns:
        Tuple[Optional[str], Set[str]]: An error message, which is None
            if the operation was successful, and a set of invalid user
            emails.
    """

    error_msg, client = get_client()
    if error_msg is not None:
        return error_msg, set()

    # remove existing tag from deleted emails
    # remove first because there are no errors here
    if tournament_tag is not None and remove_emails is not None:
        for email in remove_emails:
            # remove the tournament tag
            subscriber_hash = _get_subscriber_hash(email)
            try:
                client.lists.update_list_member_tags(
                    audience_id,
                    subscriber_hash,
                    {"tags": [{"name": tournament_tag, "status": "inactive"}]},
                )
            except ApiClientError as ex:
                # most likely error is that the user doesn't exist; ignore
                error_msg = ex.text
                print(
                    f"Error while removing tag {tournament_tag!r} from "
                    f"{email!r}: {error_msg}"
                )

    invalid_emails = set()

    tags_kwargs = {}
    if tournament_tag is not None:
        tags_kwargs["tags"] = [tournament_tag]
    for email in emails:
        # add user and tag if doesn't exist
        try:
            client.lists.set_list_member(
                audience_id,
                email,
                {
                    "email_address": email,
                    # even if they were previously unsubscribed,
                    # re-subscribe them for this tournament
                    # if they unsubscribed for this tournament, oops...
                    "status": "subscribed",
                    **tags_kwargs,
                },
            )
        except ApiClientError as ex:
            error_msg = ex.text
            if "Please provide a valid email address." in str(error_msg):
                # invalid email address
                print("Invalid email address:", email)
                invalid_emails.add(email)
            else:
                print("Adding member error:", error_msg)
                return error_msg, set()

    return None, invalid_emails


# =============================================================================

CAMPAIGN_FOLDER_FIELDS = {
    "id": {"path": "id"},
    "name": {"path": "name"},
    "num_campaigns": {"path": "count"},
}


def get_campaign_folders():
    """Gets the Mailchimp campaign folders.

    Returns:
        Union[Tuple[str, None], Tuple[None, List[Dict]]]:
            A tuple of an error message, or a list of campaign folder
            infos in the format:
                'id': folder id
                'name': folder name
                'num_campaigns': number of campaigns in the folder
    """
    error_msg, client = get_client()
    if error_msg is not None:
        return error_msg, None
    return _get_paginated_data(
        client.campaignFolders.list, CAMPAIGN_FOLDER_FIELDS, "folders"
    )


def get_campaign_folder(folder_id):
    """Gets the requested campaign folder.

    Returns:
        Union[Tuple[str, None], Tuple[None, Dict]]:
            An error message, or the campaign folder info in the format:
                'id': folder id
                'name': folder name
                'num_campaigns': number of campaigns in the folder
    """
    error_msg, client = get_client()
    if error_msg is not None:
        return error_msg, None
    return _get_resource(
        client.campaignFolders.get, folder_id, CAMPAIGN_FOLDER_FIELDS
    )


# =============================================================================

CAMPAIGN_FIELDS = {
    "id": {"path": "id"},
    "title": {"path": ["settings", "title"]},
}


def get_campaigns_in_folder(folder_id):
    """Gets the Mailchimp campaigns in the given folder.

    Returns:
        Union[Tuple[str, None], Tuple[None, List[Dict]]]:
            A tuple of an error message, or a list of campaigns in the
            format:
                'id': campaign id
                'title': campaign title
    """
    error_msg, client = get_client()
    if error_msg is not None:
        return error_msg, None
    return _get_paginated_data(
        client.campaigns.list,
        CAMPAIGN_FIELDS,
        "campaigns",
        folder_id=folder_id,
    )
