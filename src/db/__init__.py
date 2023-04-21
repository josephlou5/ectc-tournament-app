"""
Methods and objects pertaining to the database.
"""

# =============================================================================

from flask_migrate import Migrate

from db import (
    admin,
    global_state,
    match_status,
    roster,
    sent_emails,
    subscriptions,
)
from db.models import db

# =============================================================================

__all__ = (
    "db",
    "global_state",
    "admin",
    "roster",
    "subscriptions",
    "match_status",
    "sent_emails",
)

# =============================================================================


def init_app(app):
    db.init_app(app)
    Migrate(app, db)
