"""
Views for the super admin role.
"""

# =============================================================================

from flask import flash, request

import db
from utils.auth import login_required
from utils.server import AppRoutes, _render, get_request_json, unsuccessful

# =============================================================================

app = AppRoutes()

# =============================================================================


@app.route("/manage_admins", methods=["GET", "POST", "DELETE"])
@login_required(super_admin=True)
def manage_admins():
    if request.method == "POST":
        error_msg, request_args = get_request_json("email")
        if error_msg is not None:
            return unsuccessful(error_msg)
        email = request_args["email"]
        if email == "":
            return unsuccessful("Email is empty")

        print(" ", "Adding email as admin:", email)

        if db.admin.is_admin(email):
            success_msg = f"Already an admin: {email}"
            print(" ", success_msg)
            flash(success_msg, "manage-admins.success")
            return {"success": True}

        success = db.admin.add_admin(email)
        if not success:
            return unsuccessful("Database error", "Saving admin")

        success_msg = f"Successfully added admin: {email}"
        print(" ", success_msg)
        flash(success_msg, "manage-admins.success")

        return {"success": True}

    if request.method == "DELETE":
        # all error messages are flashed

        error_msg, request_args = get_request_json("email")
        if error_msg is not None:
            flash(error_msg, "manage-admins.danger")
            return unsuccessful(error_msg)
        email = request_args["email"]
        if email == "":
            error_msg = "Email is empty"
            flash(error_msg, "manage-admins.danger")
            return unsuccessful(error_msg)

        print(" ", "Removing email as admin:", email)

        if not db.admin.is_admin(email):
            error_msg = f"Cannot delete non-admin: {email}"
            flash(error_msg, "manage-admins.danger")
            return unsuccessful(error_msg)

        success = db.admin.remove_admin(email)
        if not success:
            error_msg = "Database error"
            flash(error_msg, "manage-admins.danger")
            return unsuccessful(error_msg, "Removing admin")

        success_msg = f"Successfully removed admin: {email}"
        print(" ", success_msg)
        flash(success_msg, "manage-admins.success")

        return {"success": True}

    # get
    all_admins = db.admin.get_all()
    return _render("super_admin/manage_admins.jinja", **all_admins)
