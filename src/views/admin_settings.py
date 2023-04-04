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


@app.route("/admin_settings", methods=["GET"])
@login_required(admin=True)
def admin_settings():
    global_state = db.global_state.get()
    super_admins = db.admin.get_all()["super_admins"]
    service_account_email = global_state.service_account_email
    tms_spreadsheet_url = None
    spreadsheet_id = global_state.tms_spreadsheet_id
    if spreadsheet_id is not None:
        tms_spreadsheet_url = fetch_tms.id_to_url(spreadsheet_id)
    has_mc_api_key = db.global_state.has_mailchimp_api_key()
    mc_audience_tag = global_state.mailchimp_audience_tag
    return _render(
        "admin_settings/index.jinja",
        super_admins=super_admins,
        service_account_email=service_account_email,
        tms_spreadsheet_url=tms_spreadsheet_url,
        has_mc_api_key=has_mc_api_key,
        mc_audience_tag=mc_audience_tag,
    )


@app.route("/admin_settings/tms_spreadsheet", methods=["POST", "DELETE"])
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
    url = request_args["url"].strip()
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


@app.route("/mailchimp/audiences", methods=["GET"])
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
            print(" ", "No selected audience in database")
        else:
            print(
                " ",
                "Selected audience id from database:",
                selected_audience_id,
            )
            for info in audiences:
                if info["id"] == selected_audience_id:
                    print(
                        " ",
                        " ",
                        f'Selected audience: {info["name"]!r} ({info["id"]})',
                    )
                    break
            else:
                # invalid audience id
                # clear from database (don't care if failed)
                _ = db.global_state.clear_mailchimp_audience_id()
                selected_audience_id = None
                print(
                    " ", " ", "Invalid selected audience id (not in fetched)"
                )

    audiences_html = render_template(
        "admin_settings/audiences_info.jinja",
        audiences=audiences,
        selected_audience_id=selected_audience_id,
    )
    return {"success": True, "audiences_html": audiences_html}


@app.route("/mailchimp/audiences/current", methods=["POST"])
@login_required(admin=True, save_redirect=False)
def set_mailchimp_audience():
    error_msg, request_args = get_request_json("audienceId")
    if error_msg is not None:
        return unsuccessful(error_msg)
    audience_id = request_args["audienceId"].strip()
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


@app.route("/mailchimp/tag/current", methods=["POST"])
@login_required(admin=True, save_redirect=False)
def set_mailchimp_audience_tag():
    error_msg, request_args = get_request_json("tag")
    if error_msg is not None:
        return unsuccessful(error_msg)
    audience_tag = request_args["tag"].strip()

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


@app.route("/mailchimp/template_folders", methods=["GET"])
@login_required(admin=True, save_redirect=False)
def get_mailchimp_template_folders():
    if not db.global_state.has_mailchimp_api_key():
        return unsuccessful("No Mailchimp API key")

    # fetch campaign folders
    error_msg, folders = mailchimp_utils.get_campaign_folders()
    if error_msg is not None:
        return unsuccessful(
            error_msg, "Error while fetching Mailchimp campaign folders"
        )

    if len(folders) == 0:
        print(" ", "Fetched 0 folders")
        selected_folder_id = None
    else:
        print(" ", "Fetched folders:")
        print_records(folders[0].keys(), folders, indent=4, padding=2)

        # determine which folder to select as default
        selected_folder_id = db.global_state.get_mailchimp_folder_id()
        if selected_folder_id is None:
            print(" ", "No selected folder in database")
        else:
            print(
                " ",
                "Selected folder id from database:",
                selected_folder_id,
            )
            for info in folders:
                if info["id"] == selected_folder_id:
                    print(
                        " ",
                        " ",
                        f'Selected folder: {info["name"]!r} ({info["id"]})',
                    )
                    break
            else:
                # invalid folder id
                # clear from database (don't care if failed)
                _ = db.global_state.clear_mailchimp_folder_id()
                selected_folder_id = None
                print(" ", " ", "Invalid selected folder id (not in fetched)")

    folders_html = render_template(
        "admin_settings/template_folders_info.jinja",
        folders=folders,
        selected_folder_id=selected_folder_id,
    )
    return {"success": True, "folders_html": folders_html}


@app.route("/mailchimp/template_folders/current", methods=["POST"])
@login_required(admin=True, save_redirect=False)
def set_mailchimp_template_folder():
    error_msg, request_args = get_request_json("folderId")
    if error_msg is not None:
        return unsuccessful(error_msg)
    folder_id = request_args["folderId"].strip()
    if folder_id == "":
        return unsuccessful("Folder id is empty")

    print(" ", "Setting Mailchimp template folder id:", folder_id)

    # verify folder id
    error_msg, _ = mailchimp_utils.get_campaign_folder(folder_id)
    if error_msg is not None:
        print(" ", "Template folder id verification failed:", error_msg)
        # the error message returned by the API is a bit too detailed
        # and clunky, so just keep it simple for the user
        return {"success": False, "reason": "Invalid folder id"}

    # save in database
    success = db.global_state.set_mailchimp_folder_id(folder_id)
    if not success:
        return unsuccessful("Database error", "Saving folder id")

    return {"success": True}
