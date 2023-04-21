"""
Helper methods for the EmailSent and BlastEmailSent tables.
"""

# =============================================================================

import utils
from db._utils import clear_tables, query
from db.models import BlastEmailSent, EmailSent, db

# =============================================================================


def clear_sent_emails():
    """Clears the sent emails.

    Returns:
        bool: Whether the operation was successful.
    """
    clear_tables(EmailSent, BlastEmailSent)
    return True


# =============================================================================


def add_emails_sent(emails_sent):
    """Stores the given emails as being sent.

    Returns:
        bool: Whether the operation was successful.
    """
    if len(emails_sent) == 0:
        return True
    for email_sent_info in emails_sent:
        email_sent = EmailSent(**email_sent_info)
        db.session.add(email_sent)
    db.session.commit()
    return True


def add_blast_emails_sent(emails_sent):
    """Stores the given blast emails as being sent.

    Returns:
        bool: Whether the operation was successful.
    """
    if len(emails_sent) == 0:
        return True
    for email_sent_info in emails_sent:
        email_sent = BlastEmailSent(**email_sent_info)
        db.session.add(email_sent)
    db.session.commit()
    return True


# =============================================================================


def get_all_sent_emails(tz=utils.EASTERN_TZ):
    """Returns all the sent emails, sorted by time sent (most recent
    first).

    Returns:
        List[Dict]: The sent emails in the format:
            'template_name': the Mailchimp template used
            'subject': the email subject
            'time_sent': when the email was sent (as a string)
            'blast': whether the email was a blast email
            'match_number': if not a blast email, the match number
            'recipients':
                if a blast email, a string describing the recipients
                otherwise, a list of recipient emails
    """

    emails_sent = []
    for email_sent in query(EmailSent).all():
        emails_sent.append(
            {
                "template_name": email_sent.template_name,
                "subject": email_sent.subject,
                "time_sent": utils.dt_str(
                    utils.dt_to_timezone(email_sent.time_sent, tz)
                ),
                "blast": False,
                "match_number": email_sent.match_number,
                "recipients": email_sent.email_recipients(),
            }
        )
    for email_sent in query(BlastEmailSent).all():
        emails_sent.append(
            {
                "template_name": email_sent.template_name,
                "subject": email_sent.subject,
                "time_sent": utils.dt_str(
                    utils.dt_to_timezone(email_sent.time_sent, tz)
                ),
                "blast": True,
                "recipients": email_sent.recipient,
            }
        )

    return sorted(emails_sent, key=lambda e: e["time_sent"], reverse=True)
