"""
Helper methods for the match status, which includes the MatchStatus and
EmailSent tables.
"""

# =============================================================================

from datetime import datetime

import utils
from db._utils import _set, query
from db.models import EmailSent, TMSMatchStatus, db

# =============================================================================


class _ContainsEverything:
    """A dummy class that acts like it contains any element.

    It also has a union method that returns the union of all the given
    sets.
    """

    def __contains__(self, item):
        return True

    def union(self, *iterables):
        return set().union(*iterables)


def _get_all_tms_match_statuses(match_numbers_filter=None):
    """Returns all the rows of the TMSMatchStatus table as a mapping
    from match number to TMSMatchStatus object, optionally filtering by
    the given iterable of match numbers.
    """
    if match_numbers_filter is None or isinstance(
        match_numbers_filter, _ContainsEverything
    ):
        return {
            match_status.match_number: match_status
            for match_status in query(TMSMatchStatus).all()
        }
    match_numbers_filter = set(match_numbers_filter)
    if len(match_numbers_filter) == 0:
        return {}
    if len(match_numbers_filter) == 1:
        # fetch the single match instead of iterating over everything
        match_status = query(
            TMSMatchStatus, {"match_number": next(iter(match_numbers_filter))}
        ).first()
        if match_status is None:
            return {}
        return {match_status.match_number: match_status}
    return {
        match_status.match_number: match_status
        for match_status in query(TMSMatchStatus).all()
        if match_status.match_number in match_numbers_filter
    }


# =============================================================================


def get_matches_status(match_numbers=None, tz=utils.EASTERN_TZ):
    """Gets the status for each match.

    If no match numbers are given, returns all the match numbers that
    have data in the database.

    All datetimes will be in the given timezone.

    Returns:
        Dict[int, Dict]: A mapping from match numbers to statuses in the
            format:
                'number': match number
                'tms_status': the match status from the TMS spreadsheet
                'tms_status_last_updated':
                    when the TMS status was last updated
                'emails': a list of emails sent for this match, sorted
                    by time sent, in the format:
                        'match_number': the target match number
                        'subject': the email subject
                        'recipients': a list of recipient emails
                        'template_name': the Mailchimp template used
                        'time_sent': when the email was sent
    """

    if match_numbers is None:
        match_numbers = _ContainsEverything()
    else:
        match_numbers = set(match_numbers)
        if len(match_numbers) == 0:
            return {}

    # get the statuses
    # maps: match number -> tms match status object
    tms_match_statuses = _get_all_tms_match_statuses(match_numbers)

    # get the emails
    # maps: match number -> list of email objects
    emails_sent = {}
    for email_sent in query(EmailSent).all():
        match_number = email_sent.match_number
        if match_number not in match_numbers:
            continue
        if match_number not in emails_sent:
            emails_sent[match_number] = []
        emails_sent[match_number].append(email_sent)

    # combine into a single status for each seen match
    match_status_infos = {}
    for match_number in match_numbers.union(
        tms_match_statuses.keys(), emails_sent.keys()
    ):
        status_info = {"number": match_number}
        match_status = tms_match_statuses.get(match_number, None)
        if match_status is None:
            status_info.update(
                {"tms_status": None, "tms_status_last_updated": None}
            )
        else:
            status_info.update(
                {
                    "tms_status": match_status.status,
                    "tms_status_last_updated": utils.dt_str(
                        utils.dt_to_timezone(match_status.last_updated, tz)
                    ),
                }
            )
        match_emails_sent = emails_sent.get(match_number, [])
        if match_emails_sent is None:
            status_info["emails"] = []
        else:
            status_info["emails"] = [
                {
                    "match_number": email_sent.match_number,
                    "subject": email_sent.subject,
                    "recipients": email_sent.email_recipients(),
                    "template_name": email_sent.template_name,
                    "time_sent": utils.dt_str(
                        utils.dt_to_timezone(email_sent.time_sent, tz)
                    ),
                }
                for email_sent in sorted(
                    match_emails_sent, key=lambda e: e.time_sent
                )
            ]
        match_status_infos[match_number] = status_info

    return match_status_infos


# =============================================================================


def set_matches_tms_status(matches_info):
    """Saves the TMS status for all the given matches with the current
    timestamp as the time fetched.

    Args:
        matches_info (Dict[int, str]): A mapping from match number to
            TMS status.
        time_fetched (datetime): When the TMS spreadsheet was fetched
            with this information.

    Returns:
        bool: Whether the operation was successful.
    """
    if len(matches_info) == 0:
        return True
    time_fetched = datetime.utcnow()
    match_statuses = _get_all_tms_match_statuses(matches_info.keys())
    any_changed = False
    for match_number, tms_status in matches_info.items():
        if tms_status == "":
            # missing value
            continue
        # last updated time will always require database commit
        any_changed = True
        match_status = match_statuses.get(match_number, None)
        if match_status is None:
            # create new
            match_status = TMSMatchStatus(match_number)
            db.session.add(match_status)
        _set(
            match_status,
            commit=False,
            status=tms_status,
            last_updated=time_fetched,
        )
    if any_changed:
        db.session.commit()
    return True


def add_emails_sent(emails_sent):
    """Stores the given emails as being sent.

    Returns:
        bool: Whether the operation was successful.
    """
    for email_sent_info in emails_sent:
        email_sent = EmailSent(**email_sent_info)
        db.session.add(email_sent)
    db.session.commit()
    return True
