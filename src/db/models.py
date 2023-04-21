"""
The database and models.
"""

# =============================================================================

import json

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)

import utils

# =============================================================================

__all__ = (
    "db",
    "GlobalState",
    "Admin",
    "UserSubscription",
    "School",
    "User",
    "Team",
    "TMSMatchStatus",
    "EmailSent",
    "BlastEmailSent",
)

# =============================================================================

db = SQLAlchemy()

# =============================================================================


class GlobalState(db.Model):
    """Model for saved global state."""

    __tablename__ = "GlobalState"

    id = Column(Integer, primary_key=True)
    # The service account dict info as a string
    service_account = Column(String(), nullable=True)
    # The id of the TMS spreadsheet
    tms_spreadsheet_id = Column(String(), nullable=True)
    # The last time the roster was fetched from the TMS spreadsheet
    roster_last_fetched_time = Column(DateTime(timezone=False), nullable=True)
    # The last successful matches query
    last_matches_query = Column(String(), nullable=True)
    # The Mailchimp API key
    mailchimp_api_key = Column(String(), nullable=True)
    # The id of the currently selected Mailchimp audience
    mailchimp_audience_id = Column(String(), nullable=True)
    # A Mailchimp audience tag
    mailchimp_audience_tag = Column(String(), nullable=True)
    # The id of the currently selected Mailchimp template folder
    # NOTE: For now, the template folder is actually a campaign folder,
    #   but the column name shouldn't have to change if this gets fixed.
    mailchimp_folder_id = Column(String(), nullable=True)
    # The id of the last selected Mailchimp template for match notifs
    # NOTE: For now, this is actually a campaign id, but the column name
    #   shouldn't have to change if this gets fixed.
    mailchimp_match_template_id = Column(String(), nullable=True)
    # The subject of the last sent Mailchimp email for match notifs
    mailchimp_match_subject = Column(String(), nullable=True)
    # The id of the last selected Mailchimp template for blast notifs
    # NOTE: For now, this is actually a campaign id, but the column name
    #   shouldn't have to change if this gets fixed.
    mailchimp_blast_template_id = Column(String(), nullable=True)
    # The subject of the last sent Mailchimp email for blast notifs
    mailchimp_blast_subject = Column(String(), nullable=True)
    # Whether to also send notifications to coaches
    send_to_coaches = Column(Boolean(), nullable=False, default=False)
    # Whether to also send notifications to spectators
    send_to_spectators = Column(Boolean(), nullable=False, default=False)
    # Whether to also send notifications to team subscribers
    send_to_subscribers = Column(Boolean(), nullable=False, default=True)

    @property
    def service_account_info(self):
        """Returns the service account info as a dict, or None if it
        doesn't exist.
        """
        if self.service_account is None:
            return None
        return json.loads(self.service_account)

    @service_account_info.setter
    def service_account_info(self, value):
        if value is None:
            self.service_account = None
        else:
            self.service_account = utils.json_dump_compact(value)

    @property
    def service_account_email(self):
        """Returns the service account email, or None if it doesn't
        exist.
        """
        service_account_info = self.service_account_info
        if service_account_info is None:
            return None
        return service_account_info["client_email"]


# =============================================================================


class Admin(db.Model):
    """Model for an admin."""

    __tablename__ = "Admins"

    email = Column(String(), primary_key=True)
    is_super_admin = Column(Boolean(), nullable=False, default=False)

    def __init__(self, email, is_super_admin=False):
        self.email = email
        self.is_super_admin = is_super_admin


class UserSubscription(db.Model):
    """Model for a user's subscription to a team."""

    __tablename__ = "UserSubscriptions"

    id = Column(Integer, primary_key=True)
    email = Column(String(), nullable=False)
    school = Column(String(), nullable=False)
    division = Column(String(), nullable=False)
    number = Column(Integer, nullable=False)

    __table_args__ = (
        # basically, each row should be unique
        UniqueConstraint(
            "email",
            "school",
            "division",
            "number",
            name="_email_school_team_code",
        ),
    )

    def __init__(self, email, school, division, team_number):
        self.email = email
        self.school = school
        self.division = division
        self.number = team_number


# =============================================================================

# Roster models


class School(db.Model):
    """Model for a school."""

    __tablename__ = "Schools"

    id = Column(Integer, primary_key=True)
    name = Column(String(), unique=True, nullable=False)

    users = db.relationship("User", backref="school")
    teams = db.relationship("Team", backref="school")

    def __init__(self, name):
        self.name = name


class User(db.Model):
    """Model for a user (includes coaches, athletes, and spectators)."""

    __tablename__ = "Users"

    id = Column(Integer, primary_key=True)
    first_name = Column(String(), nullable=False)
    last_name = Column(String(), nullable=False)
    email = Column(String(), unique=True, nullable=False)
    email_valid = Column(Boolean(), nullable=False, default=True)
    role = Column(String(), nullable=False)
    school_id = Column(Integer, ForeignKey(School.id), nullable=False)

    def __init__(
        self, first_name, last_name, email, role, school_id, email_valid=True
    ):
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
        self.email_valid = email_valid
        self.role = role
        self.school_id = school_id

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


class Team(db.Model):
    """Model for a team."""

    __tablename__ = "Teams"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey(School.id), nullable=False)
    division = Column(String(), nullable=False)
    number = Column(Integer, nullable=False)

    # Team members
    light_id = Column(Integer, ForeignKey(User.id), nullable=True)
    middle_id = Column(Integer, ForeignKey(User.id), nullable=True)
    heavy_id = Column(Integer, ForeignKey(User.id), nullable=True)

    # A comma-separated list of user ids
    alternate_ids = Column(String(), nullable=False, default="")

    __table_args__ = (
        # could also be multi primary key, but want id for each team
        UniqueConstraint(
            "school_id", "division", "number", name="_school_team_code"
        ),
    )

    def __init__(
        self,
        school_id,
        division,
        team_number,
        light_id=None,
        middle_id=None,
        heavy_id=None,
        alternate_ids=None,
    ):
        self.school_id = school_id
        self.division = division
        self.number = team_number
        # assume the given team members have the "ATHLETE" role
        self.light_id = light_id
        self.middle_id = middle_id
        self.heavy_id = heavy_id
        if alternate_ids is None:
            alternate_ids = []
        self.alternate_ids = ",".join(map(str, sorted(alternate_ids)))

    def get_alternate_ids(self):
        """Returns a list of the alternate user ids."""
        if self.alternate_ids == "":
            return []
        return list(map(int, self.alternate_ids.split(",")))


# =============================================================================

# Match status table


class TMSMatchStatus(db.Model):
    """Model for the last known status of a match from the TMS
    spreadsheet.
    """

    __tablename__ = "TMSMatchStatuses"

    match_number = Column(Integer, primary_key=True, autoincrement=False)
    status = Column(String(), nullable=True)
    last_updated = Column(DateTime(timezone=False), nullable=True)
    # TODO: should this also include the team names?

    def __init__(self, match_number):
        self.match_number = match_number


class EmailSent(db.Model):
    """Model for when an email was sent."""

    __tablename__ = "EmailsSent"

    id = Column(Integer, primary_key=True)
    match_number = Column(Integer, nullable=False)
    # The name of the Mailchimp template used for this email
    template_name = Column(String(), nullable=False)
    subject = Column(String(), nullable=False)
    time_sent = Column(DateTime(timezone=False), nullable=False)
    # A semicolon-separated list of recipient email addresses
    recipients = Column(String(), nullable=False)

    def __init__(
        self, match_number, template_name, subject, time_sent, recipients
    ):
        self.match_number = match_number
        self.template_name = template_name
        self.subject = subject
        self.time_sent = time_sent
        self.recipients = ";".join(sorted(recipients))

    def email_recipients(self):
        return self.recipients.split(";")


class BlastEmailSent(db.Model):
    """Model for when a blast email was sent."""

    __tablename__ = "BlastEmailsSent"

    id = Column(Integer, primary_key=True)
    # The name of the Mailchimp template used for this email
    template_name = Column(String(), nullable=False)
    subject = Column(String(), nullable=False)
    time_sent = Column(DateTime(timezone=False), nullable=False)

    # At most one of these should be set; the other should be null.
    division = Column(String(), nullable=True)
    tag = Column(String(), nullable=True)

    def __init__(
        self, template_name, subject, time_sent, division=None, tag=None
    ):
        self.template_name = template_name
        self.subject = subject
        self.time_sent = time_sent
        if division is not None and tag is not None:
            raise ValueError("only one of `division` or `tag` can be set")
        self.division = division
        self.tag = tag

    @property
    def recipient(self):
        if self.tag is not None:
            return f"Tag {self.tag!r}"
        if self.division is not None:
            return f"Division {self.division!r}"
        return "Entire audience"
