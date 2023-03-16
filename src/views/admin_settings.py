"""
The "admin settings" view.
"""

# =============================================================================

from flask import flash, request

import db
from utils import fetch_tms, mailchimp_utils
from utils.routes import AppRoutes, _render

# =============================================================================

app = AppRoutes()

# =============================================================================


@app.route("/admin", methods=["GET"])
def admin_settings():
    global_state = db.global_state.get()
    service_account_email = global_state.service_account_email
    tms_spreadsheet_url = fetch_tms.id_to_url(global_state.tms_spreadsheet_id)
    return _render(
        "admin_settings/index.jinja",
        service_account_email=service_account_email,
        tms_spreadsheet_url=tms_spreadsheet_url,
    )


@app.route("/admin/service_account", methods=["POST"])
def set_service_account():
    service_account_info = request.get_json(silent=True)
    if service_account_info is None:
        print(" ", "Invalid JSON data given")
        return {"success": False, "reason": "Invalid JSON data"}

    print(" ", "Got service account info to set:", service_account_info)

    # validate the credentials
    error_msg, _ = fetch_tms.get_service_account_client(service_account_info)
    if error_msg is not None:
        print(" ", "Validation failed:", error_msg)
        return {"success": False, "reason": error_msg}

    # save in database
    success = db.global_state.set_service_account_info(service_account_info)
    if not success:
        print(" ", "Database error")
        return {"success": False, "reason": "Database error"}

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


@app.route("/admin/tms_spreadsheet", methods=["POST"])
def set_tms_spreadsheet():
    request_args = request.get_json(silent=True)
    if request_args is None:
        return {"success": False, "reason": "Invalid JSON data"}
    if not isinstance(request_args, dict):
        return {
            "success": False,
            "reason": "Invalid JSON data: expected mapping",
        }
    if "url" not in request_args:
        return {
            "success": False,
            "reason": 'Invalid JSON data: missing "url" key',
        }
    url = request_args["url"]
    if not isinstance(url, str):
        return {
            "success": False,
            "reason": 'Invalid JSON data: expected string for "url" key',
        }

    print(" ", "Got TMS spreadsheet to set:", url)

    # validate the url
    spreadsheet_id = fetch_tms.url_to_id(url)
    if spreadsheet_id is None:
        error_msg = "Invalid spreadsheet link"
        print(" ", "Error:", error_msg)
        return {"success": False, "reason": error_msg}

    # use service account to verify access to spreadsheet
    service_account_info = db.global_state.get_service_account_info()
    if service_account_info is not None:
        print(
            " ",
            "Has service account in database; verifying spreadsheet access",
        )
        error_msg, _ = fetch_tms.get_tms_spreadsheet(spreadsheet_id)
        if error_msg is not None:
            print(" ", "Error:", error_msg)
            return {"success": False, "reason": error_msg}
        print(" ", "Verified: Service account can access url")

    # save in database
    success = db.global_state.set_tms_spreadsheet_id(spreadsheet_id)
    if not success:
        print(" ", "Database error")
        return {"success": False, "reason": "Database error"}

    success_msg = "Successfully saved TMS spreadsheet"
    print(" ", success_msg)
    # use flash so the clean url is updated
    flash(success_msg, "tms-spreadsheet.success")

    if service_account_info is None:
        # only show this flash if the save to the database was
        # successful
        flash(
            (
                "<strong>Warning:</strong> No service account; could not "
                "verify access"
            ),
            "tms-spreadsheet.warning",
        )

    return {"success": True}


@app.route("/admin/mailchimp/api_key", methods=["POST"])
def set_mailchimp_api_key():
    request_args = request.get_json(silent=True)
    if request_args is None:
        return {"success": False, "reason": "Invalid JSON data"}
    if not isinstance(request_args, dict):
        return {
            "success": False,
            "reason": "Invalid JSON data: expected mapping",
        }
    if "apiKey" not in request_args:
        return {
            "success": False,
            "reason": 'Invalid JSON data: missing "apiKey" key',
        }
    api_key = request_args["apiKey"]
    if not isinstance(api_key, str):
        return {
            "success": False,
            "reason": 'Invalid JSON data: expected string for "apiKey" key',
        }
    if api_key == "":
        return {"success": False, "reason": "API key is empty"}

    print(" ", "Setting Mailchimp API key (not printed for security)")

    # validate the client
    error_msg, _ = mailchimp_utils.get_client(api_key)
    if error_msg is not None:
        print(" ", "Validation failed:", error_msg)
        # the error message returned by the API is a bit too detailed
        # and clunky, so just keep it simple for the user
        return {"success": False, "reason": "Invalid API key"}

    # save in database
    success = db.global_state.set_mailchimp_api_key(api_key)
    if not success:
        print(" ", "Database error")
        return {"success": False, "reason": "Database error"}

    flash("Success", "mailchimp-api-key.success")
    return {"success": True}
