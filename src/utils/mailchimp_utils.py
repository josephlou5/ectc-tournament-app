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

TNS_SEGMENT_NAME = "[TNS] Match Segment"

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


def _yield_paginated_data(api_call, fields, data_key, *args, **kwargs):
    """Yields the paginated data, but does not handle API errors."""

    total_items = None
    seen_items = 0

    kwargs.update(
        {
            "fields": _get_fields_list(fields, prefix=data_key),
            "count": PAGINATION_LIMIT,
        }
    )

    while True:
        response = api_call(*args, **kwargs, offset=seen_items)
        if total_items is None:
            total_items = response["total_items"]
        paginated = response[data_key]

        for data in paginated:
            yield _extract_fields(fields, data)

        seen_items += len(paginated)
        if seen_items >= total_items:
            break


def _get_paginated_data(
    api_call, fields, data_key, *args, sort_fields=None, **kwargs
):
    try:
        all_data = list(
            _yield_paginated_data(api_call, fields, data_key, *args, **kwargs)
        )
    except ApiClientError as ex:
        error_msg = str(ex.text)
        print("Mailchimp API error:", error_msg)
        return error_msg, None
    if sort_fields is not None:
        all_data.sort(key=lambda x: tuple(x[field] for field in sort_fields))
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
                'last_sent': the datetime of the last sent campaign
    """
    error_msg, client = get_client()
    if error_msg is not None:
        return error_msg, None
    # https://mailchimp.com/developer/marketing/api/lists/get-lists-info/
    return _get_paginated_data(
        client.lists.get_all_lists,
        AUDIENCE_FIELDS,
        "lists",
        sort_fields=("name", "last_sent", "id"),
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
                'last_sent': the datetime of the last sent campaign
    """
    error_msg, client = get_client()
    if error_msg is not None:
        return error_msg, None
    # https://mailchimp.com/developer/marketing/api/lists/get-list-info/
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
                # https://mailchimp.com/developer/marketing/api/list-member-tags/add-or-remove-member-tags/
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
            # https://mailchimp.com/developer/marketing/api/list-members/add-or-update-list-member/
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
    # https://mailchimp.com/developer/marketing/api/campaign-folders/list-campaign-folders/
    return _get_paginated_data(
        client.campaignFolders.list,
        CAMPAIGN_FOLDER_FIELDS,
        "folders",
        sort_fields=("name", "num_campaigns", "id"),
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
    # https://mailchimp.com/developer/marketing/api/campaign-folders/get-campaign-folder/
    return _get_resource(
        client.campaignFolders.get, folder_id, CAMPAIGN_FOLDER_FIELDS
    )


# =============================================================================

CAMPAIGN_FIELDS = {
    "id": {"path": "id"},
    "title": {"path": ["settings", "title"]},
    "audience_id": {"path": ["recipients", "list_id"]},
    "folder_id": {"path": ["settings", "folder_id"]},
}


def get_campaigns_in_folder(folder_id):
    """Gets the Mailchimp campaigns in the given folder.

    Returns:
        Union[Tuple[str, None], Tuple[None, List[Dict]]]:
            A tuple of an error message, or a list of campaigns in the
            format:
                'id': campaign id
                'title': campaign title
                'audience_id': the audience the campaign belongs to
                    (could be blank)
                'folder_id': the campaign folder the campaign belongs to
                    (could be blank)
    """
    error_msg, client = get_client()
    if error_msg is not None:
        return error_msg, None
    # https://mailchimp.com/developer/marketing/api/campaigns/list-campaigns/
    return _get_paginated_data(
        client.campaigns.list,
        CAMPAIGN_FIELDS,
        "campaigns",
        folder_id=folder_id,
        sort_fields=("title", "audience_id", "folder_id", "id"),
    )


def get_campaign(campaign_id):
    """Gets a campaign.

    Returns:
        Union[Tuple[str, None], Tuple[None, Dict]]:
            An error message, or the campaign info in the format:
                'id': campaign id
                'title': campaign title
                'audience_id': the audience the campaign belongs to
                    (could be blank)
                'folder_id': the campaign folder the campaign belongs to
                    (could be blank)
    """
    error_msg, client = get_client()
    if error_msg is not None:
        return error_msg, None
    # https://mailchimp.com/developer/marketing/api/campaigns/get-campaign-info/
    return _get_resource(client.campaigns.get, campaign_id, CAMPAIGN_FIELDS)


# =============================================================================

SEGMENT_FIELDS = {
    "id": {"path": "id"},
    "name": {"path": "name"},
}


def get_segment_id(audience_id, segment_name):
    """Gets the id of the segment with the given name.

    Returns:
        Union[Tuple[str, None], Tuple[None, Optional[int]]]:
            An error message, or the segment id if it exists (None
            otherwise).
    """

    error_msg, client = get_client()
    if error_msg is not None:
        return error_msg, None

    # get all static segments
    try:
        # https://mailchimp.com/developer/marketing/api/list-segments/list-segments/
        for segment_info in _yield_paginated_data(
            client.lists.list_segments,
            SEGMENT_FIELDS,
            "segments",
            audience_id,
            type="static",
        ):
            if segment_info["name"] == segment_name:
                # found the segment
                return None, segment_info["id"]
    except ApiClientError as ex:
        error_msg = str(ex.text)
        print("Mailchimp API error:", error_msg)
        return error_msg, None

    # didn't find the segment; return None for segment id
    return None, None


def get_or_create_tns_segment(audience_id):
    """Gets the TNS email segment, or creates it if it doesn't exist.

    Returns:
        Union[Tuple[str, None], Tuple[None, int]]:
            An error message, or the segment id.
    """

    error_msg, client = get_client()
    if error_msg is not None:
        return error_msg, None

    error_msg, segment_id = get_segment_id(audience_id, TNS_SEGMENT_NAME)
    if error_msg is not None:
        return error_msg, None

    # create segment if not found
    if segment_id is None:
        try:
            # https://mailchimp.com/developer/marketing/api/list-segments/add-segment/
            created_segment = client.lists.create_segment(
                audience_id,
                {"name": TNS_SEGMENT_NAME, "static_segment": []},
            )
        except ApiClientError as ex:
            error_msg = str(ex.text)
            print("Mailchimp API error while creating segment:", error_msg)
            return error_msg, None
        segment_id = created_segment["id"]

    return None, segment_id


def update_tns_segment_emails(audience_id, segment_id, emails):
    """Replaces the emails in the given segment with the given emails.

    Assumes the given segment is the reserved TNS segment.

    Returns:
        Union[str, None]: An error message if an error occurred.
    """
    INVALID_EMAILS_MSG = (
        "None of the emails provided were subscribed to the list"
    )

    error_msg, client = get_client()
    if error_msg is not None:
        return error_msg

    # edit the emails in the segment
    try:
        # https://mailchimp.com/developer/marketing/api/list-segments/update-segment/
        # this call with REPLACE the emails in the segment
        # there is also a "batch add/remove members" endpoint, but you
        # would have to specify which emails to remove, so this call is
        # better because we want to start from a clean slate
        response = client.lists.update_segment(
            audience_id, segment_id, {"static_segment": emails}
        )
    except ApiClientError as ex:
        error_msg = str(ex.text)
        if INVALID_EMAILS_MSG in error_msg:
            error_msg = "All given emails were not subscribed to the audience"
        print("Mailchimp API error while updating segment:", error_msg)
        return error_msg

    if response["member_count"] != len(emails):
        # some of the given emails were not in the audience
        # TODO: handle this? or does it not matter?
        pass

    return None


# =============================================================================


def create_and_send_campaign(
    audience_id, replicate_id, subject, segment_id=None
):
    """Creates and sends a campaign in the given audience.

    Replicates the given campaign, then sets the subject, preview, and
    title, and sets the recipients to be the optionally given segment.

    Returns:
        Union[Tuple[str, None], Tuple[None, Dict]]:
            An error message, or the info of the created campaign
            (before the send).
    """

    error_msg, client = get_client()
    if error_msg is not None:
        return error_msg, None

    # replicate campaign
    try:
        # https://mailchimp.com/developer/marketing/api/campaigns/replicate-campaign/
        new_campaign = client.campaigns.replicate(replicate_id)
    except ApiClientError as ex:
        error_msg = str(ex.text)
        print(
            f"Mailchimp API error while replicating campaign {replicate_id}:",
            error_msg,
        )
        return error_msg, None
    campaign_id = new_campaign["id"]

    # update campaign info
    segment_args = {}
    if segment_id is not None:
        segment_args["saved_segment_id"] = segment_id
    try:
        # https://mailchimp.com/developer/marketing/api/campaigns/update-campaign-settings/
        campaign_info = client.campaigns.update(
            campaign_id,
            {
                "recipients": {
                    "list_id": audience_id,
                    # attach optional segment (or clear the segment)
                    "segment_opts": segment_args,
                },
                "settings": {
                    "subject_line": subject,
                    "preview_text": subject,
                    "title": f"[TNS] {subject}",
                    # don't leave this copy in the template folder
                    "folder_id": "",
                },
            },
        )
    except ApiClientError as ex:
        error_msg = str(ex.text)
        print(
            (
                "Mailchimp API error while updating settings for campaign "
                f"{campaign_id}:"
            ),
            error_msg,
        )
        return error_msg, None

    # send campaign
    try:
        # https://mailchimp.com/developer/marketing/api/campaigns/send-campaign/
        client.campaigns.send(campaign_id)
    except ApiClientError as ex:
        error_msg = str(ex.text)
        print(
            f"Mailchimp API error while sending campaign {campaign_id}:",
            error_msg,
        )
        return error_msg, None

    return None, campaign_info


def create_and_send_match_campaign(
    audience_id, replicate_id, subject, segment_id, emails
):
    """Creates and sends a campaign to the given emails.

    Updates the given segment to be the given emails, then calls
    `create_and_send_campaign()`.

    Returns:
        Union[Tuple[str, None], Tuple[None, Dict]]:
            An error message, or the info of the created campaign
            (before the send).
    """

    # update segment emails
    error_msg = update_tns_segment_emails(audience_id, segment_id, emails)
    if error_msg is not None:
        return error_msg, None

    return create_and_send_campaign(
        audience_id, replicate_id, subject, segment_id
    )
