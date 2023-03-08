"""
All the views for the app.
"""

# =============================================================================

from views import admin_settings, notifications, shared

# =============================================================================

# Lists all the tabs on the navbar in the format (endpoint func, label)
NAVBAR_TABS = [
    ("admin_settings", "Admin Settings"),
    ("notifications", "Notifications"),
]

# =============================================================================


def register_all(app):
    """Registers all the defined routes to the app."""

    for module in (shared, admin_settings, notifications):
        module.app.register(app)
