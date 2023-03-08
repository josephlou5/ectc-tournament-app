"""
The database and models.
"""

# =============================================================================

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
    # The url of the roster spreadsheet that was last fetched
    last_roster_spreadsheet = Column(String(), nullable=True)
    # The time the roster spreadsheet was last fetched
    last_fetched_time = Column(DateTime(timezone=False), nullable=True)

    def last_fetched_tz(self, tz=EASTERN_TZ):
        """Returns the last fetched time in the specified timezone."""
        if self.last_fetched_time is None:
            return None
        if isinstance(tz, str):
            tz = pytz.timezone(tz)
        dt_utc = UTC_TZ.localize(self.last_fetched_time)
        dt_local = dt_utc.astimezone(tz)
        return dt_local
