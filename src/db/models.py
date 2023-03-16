"""
The database and models.
"""

# =============================================================================

import json

import pytz
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import (
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
)

# =============================================================================

db = SQLAlchemy()

# =============================================================================

UTC_TZ = pytz.utc
EASTERN_TZ = pytz.timezone("US/Eastern")

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
    # The Mailchimp API key
    mailchimp_api_key = Column(String(), nullable=True)

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

    def roster_last_fetched_tz(self, tz=EASTERN_TZ):
        """Returns the last fetched time in the specified timezone."""
        if self.roster_last_fetched_time is None:
            return None
        if isinstance(tz, str):
            tz = pytz.timezone(tz)
        dt_utc = UTC_TZ.localize(self.roster_last_fetched_time)
        dt_local = dt_utc.astimezone(tz)
        return dt_local


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
    name = Column(String(), nullable=False)
    email = Column(String(), unique=True, nullable=False)
    role = Column(String(), nullable=False)
    school_id = Column(Integer, ForeignKey(School.id), nullable=False)

    def __init__(self, name, email, role, school_id):
        self.name = name
        self.email = email
        self.role = role
        self.school_id = school_id


class Team(db.Model):
    """Model for a team."""

    __tablename__ = "Teams"

    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey(School.id), nullable=False)
    code = Column(String(), nullable=False)

    # Team members
    light_id = Column(Integer, ForeignKey(User.id), nullable=True)
    middle_id = Column(Integer, ForeignKey(User.id), nullable=True)
    heavy_id = Column(Integer, ForeignKey(User.id), nullable=True)

    # A comma-separated list of user ids
    alternate_ids = Column(String(), nullable=False, default="")

    __table_args__ = (
        # could also be multi primary key, but want id for each team
        UniqueConstraint("school_id", "code", name="_school_team_code"),
    )

    def __init__(
        self,
        school_id,
        team_code,
        light_id=None,
        middle_id=None,
        heavy_id=None,
        alternate_ids=None,
    ):
        self.school_id = school_id
        self.code = team_code
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
