"""
Views for the super admin role.
"""

# =============================================================================

from flask import flash, request

import db
from utils import fetch_tms, mailchimp_utils
from utils.auth import login_required
from utils.server import AppRoutes, _render, get_request_json, unsuccessful
from views import notifications

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


# =============================================================================

# Global Settings page


@app.route("/global_settings", methods=["GET"])
@login_required(super_admin=True)
def global_settings():
    service_account_email = db.global_state.get_service_account_email()
    has_mc_api_key = db.global_state.has_mailchimp_api_key()
    return _render(
        "super_admin/global_settings.jinja",
        service_account_email=service_account_email,
        has_mc_api_key=has_mc_api_key,
    )


@app.route("/global_settings/service_account", methods=["POST", "DELETE"])
@login_required(super_admin=True, save_redirect=False)
def set_service_account():
    if request.method == "DELETE":
        print(" ", "Clearing service account info")
        success = db.global_state.clear_service_account_info()
        if not success:
            error_msg = "Database error"
            print(" ", "Error:", error_msg)
            flash(error_msg, "service-account.danger")
        else:
            success_msg = "Successfully cleared service account"
            print(" ", success_msg)
            flash(success_msg, "service-account.success")
        return {"success": success}

    error_msg, service_account_info = get_request_json(top_level=dict)
    if error_msg is not None:
        return unsuccessful(error_msg)

    print(" ", "Got service account info to set:", service_account_info)

    # validate the credentials
    error_msg, _ = fetch_tms.get_service_account_client(service_account_info)
    if error_msg is not None:
        return unsuccessful(error_msg, "Invalid service account info")

    # save in database
    success = db.global_state.set_service_account_info(service_account_info)
    if not success:
        return unsuccessful("Database error", "Saving service account")

    success_msg = "Successfully set service account"
    print(" ", success_msg)
    # use flash so the service account email is updated
    flash(success_msg, "service-account.success")

    # verify access to TMS spreadsheet
    spreadsheet_id = db.global_state.get_tms_spreadsheet_id()
    if spreadsheet_id is not None:
        print(
            " ",
            "Has TMS spreadsheet in database; verifying spreadsheet access",
        )
        error_msg, _ = fetch_tms.get_tms_spreadsheet(spreadsheet_id)
        if error_msg is not None:
            print(" ", "Error:", error_msg)
            flash(
                (
                    "<strong>Error:</strong> Could not access TMS "
                    f"spreadsheet: {error_msg}"
                ),
                "service-account.warning",
            )
        else:
            print(" ", "Verified: Service account can access TMS spreadsheet")

    return {"success": True}


@app.route("/mailchimp/api_key", methods=["POST", "DELETE"])
@login_required(super_admin=True, save_redirect=False)
def set_mailchimp_api_key():
    if request.method == "DELETE":
        print(" ", "Clearing Mailchimp API key (and other related values)")
        # clear the global client so that other operations (such as
        # populating the audience) does not use the wrong API key
        mailchimp_utils.clear_global_client()
        success = db.global_state.clear_mailchimp_related_fields()
        if not success:
            error_msg = "Database error"
            print(" ", "Error:", error_msg)
            flash(error_msg, "mailchimp-api-key.danger")
        else:
            success_msg = "Successfully cleared API key"
            print(" ", success_msg)
            flash(success_msg, "mailchimp-api-key.success")
        return {"success": success}

    error_msg, request_args = get_request_json("apiKey")
    if error_msg is not None:
        return unsuccessful(error_msg)
    api_key = request_args["apiKey"]
    if api_key == "":
        return unsuccessful("API key is empty")

    print(" ", "Setting Mailchimp API key (not printed for security)")

    # validate the client
    error_msg, _ = mailchimp_utils.get_client(api_key)
    if error_msg is not None:
        print(" ", "Invalid API key:", error_msg)
        # the error message returned by the API is a bit too detailed
        # and clunky, so just keep it simple for the user
        return {"success": False, "reason": "Invalid API key"}

    # save in database
    success = db.global_state.set_mailchimp_api_key(api_key)
    if not success:
        return unsuccessful("Database error", "Saving Mailchimp API key")

    success_msg = "Successfully set API key"
    print(" ", success_msg)
    flash(success_msg, "mailchimp-api-key.success")

    return {"success": True}


# =============================================================================


@app.route("/super_admin/clear_everything", methods=["DELETE"])
@login_required(super_admin=True, save_redirect=False)
def clear_everything():
    def _db_error(error_while):
        print(" ", " ", " ", "Database error while", error_while)
        flash("Database error", "clear-everything.danger")
        return {"success": False}

    print(" ", "Clearing all saved data")

    print(" ", " ", "Clearing admin settings")
    success = db.global_state.clear_all_admin_settings()
    if not success:
        return _db_error("clearing admin settings")

    print(" ", " ", "Clearing roster")
    success = db.roster.clear_roster()
    if not success:
        return _db_error("clearing roster")

    print(" ", " ", "Clearing matches status info")
    success = db.match_status.clear_matches_status()
    if not success:
        return _db_error("clearing matches status")

    print(" ", " ", "Deleting fetch roster logs")
    logs_file = notifications.FETCH_ROSTER_LOGS_FILE
    if logs_file.exists():
        logs_file.unlink()

    flash("Successfully cleared all data", "clear-everything.success")
    return {"success": True}
