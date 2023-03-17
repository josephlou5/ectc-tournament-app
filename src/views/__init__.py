"""
All the views for the app.
"""

# =============================================================================

from flask import url_for

from views import admin_settings, notifications, shared

# =============================================================================


class NavbarTab:
    """A tab in the navbar."""

    def __init__(self, label, endpoint_func):
        self.label = label
        self._endpoint_func = endpoint_func

    @property
    def endpoint(self):
        # assume this is only called when in an application context
        return url_for(self._endpoint_func)


# Lists all the tabs to go on the navbar
NAVBAR_TABS = [
    NavbarTab("Admin Settings", "admin_settings"),
    NavbarTab("Notifications", "notifications"),
]
# FUTURE: log in, log out, profile, etc
NAVBAR_TABS_RIGHT = []

# =============================================================================


def register_all(app):
    """Registers all the defined routes to the app."""

    for module in (shared, admin_settings, notifications):
        module.app.register(app)
