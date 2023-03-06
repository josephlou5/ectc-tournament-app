"""
The "admin settings" view.
"""

# =============================================================================

from flask import flash, request

import db
from utils import fetch_roster_data
from utils.routes import AppRoutes, _render

# =============================================================================

app = AppRoutes()

# =============================================================================


@app.route("/admin", methods=["GET"])
def admin_settings():
    service_account_email = db.global_state.get_service_account_email()
    return _render(
        "admin_settings/index.jinja",
        service_account_email=service_account_email,
    )


@app.route("/admin/service_account", methods=["POST"])
def set_service_account():
    service_account_info = request.get_json(silent=True)
    if service_account_info is None:
        print("  Invalid JSON data given")
        return {"success": False, "reason": "Invalid JSON data"}
    print("Got service account info:", service_account_info)
    error_msg, _ = fetch_roster_data.get_service_account(service_account_info)
    if error_msg is not None:
        print("  Validation failed:", error_msg)
        return {"success": False, "reason": error_msg}
    success = db.global_state.set_service_account_info(service_account_info)
    if not success:
        print("  Database error")
        return {"success": False, "reason": "Database error"}
    print("  Successfully set service account")
    # use flash so that the email also gets updated on the page
    flash("Successfully set service account")
    return {"success": True}
