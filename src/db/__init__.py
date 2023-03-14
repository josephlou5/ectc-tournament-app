"""
Methods and objects pertaining to the database.
"""

# =============================================================================

from flask_migrate import Migrate

from db import global_state, roster
from db.models import db

# =============================================================================

__all__ = (
    "db",
    "global_state",
    "roster",
)

# =============================================================================


def init_app(app):
    db.init_app(app)
    Migrate(app, db)
