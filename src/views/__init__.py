"""
All the views for the app.
"""

# =============================================================================

from views import admin_settings, shared

# =============================================================================

# Lists all the tabs on the navbar in the format (endpoint func, label)
NAVBAR_TABS = [
    ("admin_settings", "Admin Settings"),
]

# =============================================================================


def register_all(app):
    """Registers all the defined routes to the app."""

    for module in (shared, admin_settings):
        module.app.register(app)
