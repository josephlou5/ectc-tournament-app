"""
All the views for the app.
"""

# =============================================================================

from views import admin_settings, shared

# =============================================================================


def register_all(app):
    """Registers all the defined routes to the app."""

    for module in (shared, admin_settings):
        module.app.register(app)
