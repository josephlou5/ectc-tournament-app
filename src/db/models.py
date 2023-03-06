"""
The database and models.
"""

# =============================================================================

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, Integer, String

# =============================================================================

__all__ = (
    "db",
    "GlobalState",
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
    # The id of the roster spreadsheet that was most recently fetched
    latest_roster_spreadsheet = Column(String(), nullable=True)
