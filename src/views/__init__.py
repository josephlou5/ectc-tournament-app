"""
All the views for the app.
"""

# =============================================================================

from views import admin_settings, auth, notifications, shared, super_admin

# =============================================================================


def register_all(app):
    """Registers all the defined routes to the app."""

    for module in (shared, auth, super_admin, admin_settings, notifications):
        module.app.register(app)
