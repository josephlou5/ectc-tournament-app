"""
Utilities for authorization.
"""

# =============================================================================

import functools

from flask import redirect, request, session, url_for
from werkzeug.exceptions import Forbidden

import db

# =============================================================================

__all__ = (
    "_redirect_last",
    "set_redirect_page",
    "get_email",
    "is_logged_in",
    "is_logged_in_admin",
    "is_logged_in_super_admin",
    "login_required",
)

# =============================================================================


def _redirect_last():
    """Redirects to the redirect page."""
    redirect_uri = session.get("redirect_page", None)
    if redirect_uri is None:
        return redirect(url_for("index"))
    return redirect(redirect_uri)


def set_redirect_page():
    """Sets the current page as the page to redirect to."""
    session["redirect_page"] = request.path


# =============================================================================


def get_email():
    """Gets the email of the currently logged in user, or None."""
    return session.get("email", None)


def is_logged_in():
    """Returns True if a user is currently logged in."""
    return get_email() is not None


def is_logged_in_admin():
    """Returns True if the currently logged in user is an admin.

    If no user is logged in, returns False.
    """
    email = get_email()
    if email is None:
        return False
    return db.admin.is_admin(email)


def is_logged_in_super_admin():
    """Returns True if the currently logged in user is a super admin.

    If no user is logged in, returns False.
    """
    email = get_email()
    if email is None:
        return False
    return db.admin.is_super_admin(email)


# =============================================================================


def login_required(admin=False, super_admin=False, save_redirect=True):
    """A decorator to protect an endpoint with a login.

    Args:
        admin (bool): Whether the endpoint is only for admins.
        super_admin (bool): Whether the endpoint is only for super
            admins.
        save_redirect (bool): Whether to allow this endpoint to be
            redirected to upon successful login.
    """

    def login_wrapper(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if save_redirect:
                set_redirect_page()
            if not is_logged_in():
                return redirect(url_for("log_in"))
            if super_admin and not is_logged_in_super_admin():
                # not a super admin
                raise Forbidden(
                    "You do not have permission to view a super admin page."
                )
            if admin and not is_logged_in_admin():
                # not an admin
                raise Forbidden(
                    "You do not have permission to view an admin page."
                )
            return func(*args, **kwargs)

        return wrapper

    return login_wrapper