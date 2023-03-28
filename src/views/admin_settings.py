"""
The "admin settings" view.
"""

# =============================================================================

from flask import flash, render_template, request

import db
from utils import fetch_tms, mailchimp_utils
from utils.auth import login_required
from utils.server import (
    AppRoutes,
    _render,
    get_request_json,
    print_records,
    unsuccessful,
)

# =============================================================================

app = AppRoutes()

# =============================================================================


@app.route("/admin", methods=["GET"])
@login_required(admin=True)
def admin_settings():
    global_state = db.global_state.get()
    service_account_email = global_state.service_account_email
    tms_spreadsheet_url = None
    spreadsheet_id = global_state.tms_spreadsheet_id
    if spreadsheet_id is not None:
        tms_spreadsheet_url = fetch_tms.id_to_url(spreadsheet_id)
    has_mc_api_key = db.global_state.has_mailchimp_api_key()
    mc_audience_tag = global_state.mailchimp_audience_tag
    return _render(
        "admin_settings/index.jinja",
        service_account_email=service_account_email,
        tms_spreadsheet_url=tms_spreadsheet_url,
        has_mc_api_key=has_mc_api_key,
        mc_audience_tag=mc_audience_tag,
    )


@app.route("/admin/service_account", methods=["POST", "DELETE"])
@login_required(admin=True, save_redirect=False)
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


@app.route("/admin/tms_spreadsheet", methods=["POST", "DELETE"])
@login_required(admin=True, save_redirect=False)
def set_tms_spreadsheet():
    if request.method == "DELETE":
        print(" ", "Clearing TMS spreadsheet url")
        success = db.global_state.clear_tms_spreadsheet_id()
        if not success:
            error_msg = "Database error"
            print(" ", "Error:", error_msg)
            flash(error_msg, "tms-spreadsheet.danger")
        else:
            success_msg = "Successfully cleared TMS spreadsheet"
            print(" ", success_msg)
            flash(success_msg, "tms-spreadsheet.success")
        return {"success": success}

    error_msg, request_args = get_request_json("url")
    if error_msg is not None:
        return unsuccessful(error_msg)
    url = request_args["url"]
    if url == "":
        return unsuccessful("TMS spreadsheet url is empty")

    print(" ", "Got TMS spreadsheet to set:", url)

    # validate the url
    spreadsheet_id = fetch_tms.url_to_id(url)
    if spreadsheet_id is None:
        return unsuccessful("Invalid spreadsheet link")

    # use service account to verify access to spreadsheet
    service_account_info = db.global_state.get_service_account_info()
    if service_account_info is not None:
        print(
            " ",
            "Has service account in database; verifying spreadsheet access",
        )
        error_msg, _ = fetch_tms.get_tms_spreadsheet(spreadsheet_id)
        if error_msg is not None:
            return unsuccessful(error_msg)
        print(" ", "Verified: Service account can access url")

    # save in database
    success = db.global_state.set_tms_spreadsheet_id(spreadsheet_id)
    if not success:
        return unsuccessful("Database error", "Saving url")

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


@app.route("/admin/mailchimp/api_key", methods=["POST", "DELETE"])
@login_required(admin=True, save_redirect=False)
def set_mailchimp_api_key():
    if request.method == "DELETE":
        print(" ", "Clearing Mailchimp API key")
        # clear the global client so that other operations (such as
        # populating the audience) does not use the wrong API key
        mailchimp_utils.clear_global_client()
        success = db.global_state.clear_mailchimp_api_key()
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


@app.route("/admin/mailchimp/audiences", methods=["GET"])
@login_required(admin=True, save_redirect=False)
def get_mailchimp_audiences():
    if not db.global_state.has_mailchimp_api_key():
        return unsuccessful("No Mailchimp API key")

    # fetch audiences
    error_msg, audiences = mailchimp_utils.get_audiences()
    if error_msg is not None:
        return unsuccessful(
            error_msg, "Error while fetching Mailchimp audiences"
        )

    if len(audiences) == 0:
        print(" ", "Fetched 0 audiences")
        selected_audience_id = None
    else:
        print(" ", "Fetched audiences:")
        print_records(audiences[0].keys(), audiences, indent=4, padding=2)

        # determine which audience to select as default
        selected_audience_id = db.global_state.get_mailchimp_audience_id()
        if selected_audience_id is None:
            selected_audience_id = audiences[0]["id"]
            print(
                " ",
                "No selected audience in database; using first audience:",
                selected_audience_id,
            )
            # save in database (don't care if failed)
            _ = db.global_state.set_mailchimp_audience_id(selected_audience_id)
        else:
            print(
                " ",
                "Selected audience id from database:",
                selected_audience_id,
            )
            if all(selected_audience_id != info["id"] for info in audiences):
                # invalid audience id
                # clear from database (don't care if failed)
                _ = db.global_state.clear_mailchimp_audience_id()
                selected_audience_id = audiences[0]["id"]
                print(
                    " ",
                    " ",
                    (
                        "Invalid selected audience id (not in fetched); using "
                        "first audience:"
                    ),
                    selected_audience_id,
                )

    audiences_html = render_template(
        "admin_settings/audiences_info.jinja",
        audiences=audiences,
        selected_audience_id=selected_audience_id,
    )
    return {"success": True, "audiences_html": audiences_html}


@app.route("/admin/mailchimp/audiences/current", methods=["POST"])
@login_required(admin=True, save_redirect=False)
def set_mailchimp_audience():
    error_msg, request_args = get_request_json("audienceId")
    if error_msg is not None:
        return unsuccessful(error_msg)
    audience_id = request_args["audienceId"]
    if audience_id == "":
        return unsuccessful("Audience id is empty")

    print(" ", "Setting Mailchimp audience id:", audience_id)

    # verify audience id
    error_msg, _ = mailchimp_utils.get_audience(audience_id)
    if error_msg is not None:
        print(" ", "Audience id verification failed:", error_msg)
        # the error message returned by the API is a bit too detailed
        # and clunky, so just keep it simple for the user
        return {"success": False, "reason": "Invalid audience id"}

    # save in database
    success = db.global_state.set_mailchimp_audience_id(audience_id)
    if not success:
        return unsuccessful("Database error", "Saving audience id")

    return {"success": True}


@app.route("/admin/mailchimp/tag/current", methods=["POST"])
@login_required(admin=True, save_redirect=False)
def set_mailchimp_audience_tag():
    error_msg, request_args = get_request_json("tag")
    if error_msg is not None:
        return unsuccessful(error_msg)
    audience_tag = request_args["tag"]
    
    if audience_tag == "":
        # clear it instead of setting it
        print(" ", "Clearing Mailchimp audience tag (received empty)")
        success = db.global_state.clear_mailchimp_audience_tag()
        if not success:
            return unsuccessful("Database error", "Clearing audience tag")
    else:
        print(" ", "Setting Mailchimp audience tag:", audience_tag)
        success = db.global_state.set_mailchimp_audience_tag(audience_tag)
        if not success:
            return unsuccessful("Database error", "Saving audience tag")

    return {"success": True}
