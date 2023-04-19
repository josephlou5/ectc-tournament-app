"""
Contains the global Flask app instance.
"""

# =============================================================================

from flask import Flask, redirect, request
from flask_wtf.csrf import CSRFProtect
from werkzeug.exceptions import NotFound

import db
import views
from config import get_config
from utils import flask_utils
from utils.auth import (
    get_email,
    is_logged_in,
    is_logged_in_admin,
    is_logged_in_in_roster,
    is_logged_in_super_admin,
)
from utils.server import _render

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
    variables = {
        "APP_NAME": "Tournament Notification System",
        "NAVBAR_APP_NAME": "TNS",
        "get_flashed_by_categories": flask_utils.get_flashed_by_categories,
    }
    user_is_logged_in = is_logged_in()
    variables["user_is_logged_in"] = user_is_logged_in
    if user_is_logged_in:
        variables.update(
            {
                "logged_in_email": get_email(),
                "user_is_admin": is_logged_in_admin(),
                "user_is_super_admin": is_logged_in_super_admin(),
                "user_is_in_roster": is_logged_in_in_roster(),
            }
        )
    return variables


@app.before_request
def before_request():  # pylint: disable=inconsistent-return-statements
    if not request.is_secure:
        url = request.url.replace("http://", "https://", 1)
        return redirect(url, code=301)


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
