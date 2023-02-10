"""
Helpers to define routes in other files and add them to the global app
later.
"""

# =============================================================================

from flask import make_response, render_template

# =============================================================================

__all__ = (
    "AppRoutes",
    "_render",
)

# =============================================================================


class AppRoutes:
    """Contains all the routes defined in a module.

    Acts as a mock Flask "app" that can have routes added to it. For
    example:

    ```python
    # In views.py
    app = AppRoutes()

    @app.route("/", methods=["GET"])
    def index():
        return "Hello, world!"

    # In app.py
    app = Flask(__name__)
    views.app.register(app)
    ```

    In this way, routes can easily be moved to other modules without any
    other changes.
    """

    def __init__(self):
        self._routes = []

    def route(self, rule, **options):
        """A decorator to create a route.

        Accepts the same args as `@app.route()`.
        """

        def wrapper(func):
            self._routes.append((rule, func, options))
            return func

        return wrapper

    def register(self, app):
        """Registers all the routes to the app."""
        for rule, func, options in self._routes:
            app.add_url_rule(rule, view_func=func, **options)


def _render(template_file, **kwargs):
    """Renders the given template file."""
    html = render_template(template_file, **kwargs)
    response = make_response(html)
    return response
