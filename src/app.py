"""
Contains the global Flask app instance.
"""

# =============================================================================

from flask import Flask
from flask_wtf.csrf import CSRFProtect
from werkzeug.exceptions import NotFound

import db
import views
from config import get_config
from utils import flask_utils
from utils.routes import _render

# =============================================================================

# Set up app

app = Flask(__name__, instance_relative_config=True)
app.config.from_object(get_config(app.debug))

# Set up CSRF protection
CSRFProtect().init_app(app)

# Set up database
db.init_app(app)


@app.context_processor
def inject_template_variables():
    return {
        "APP_NAME": "ECTC Notification App",
        "navbar_tabs": views.NAVBAR_TABS,
        "navbar_tabs_right": views.NAVBAR_TABS_RIGHT,
        "get_flashed_by_categories": flask_utils.get_flashed_by_categories,
    }


# =============================================================================


def error_view(title, message):
    return _render("error.jinja", title=title, message=message)


@app.errorhandler(404)
@app.errorhandler(405)  # if method is not allowed, also use not found
def error_not_found(e):
    if e.code == 405:
        e = NotFound()
    return error_view("404 Not Found", e.description)


@app.errorhandler(403)
def error_forbidden(e):
    return error_view("Access denied", e.description)


# =============================================================================

# Register all views
views.register_all(app)
