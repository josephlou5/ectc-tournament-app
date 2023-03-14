"""
The database and models.
"""

# =============================================================================

import json

import pytz
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, DateTime, Integer, String

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
        # use the most compact representation
        self.service_account = json.dumps(value, separators=(",", ":"))

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
