"""
The "notifications" view, which includes fetching the roster, fetching
team info, and sending notifications.
"""

# =============================================================================

from flask import flash, request

import db
from utils import fetch_roster_data
from utils.routes import AppRoutes, _render

# =============================================================================

app = AppRoutes()

# =============================================================================


@app.route("/notifications", methods=["GET"])
def notifications():
    spreadsheet_url = db.global_state.get_last_fetched_spreadsheet_url()

    last_fetched_time = None
    last_fetched_dt = db.global_state.get_last_fetched_time()
    if last_fetched_dt is not None:
        last_fetched_time = last_fetched_dt.strftime("%Y-%m-%d %H:%M:%S")

    return _render(
        "notifications/index.jinja",
        roster_worksheet_name=fetch_roster_data.ROSTER_WORKSHEET_NAME,
        spreadsheet_url=spreadsheet_url,
        last_fetched_time=last_fetched_time,
    )


@app.route("/notifications/fetch_roster", methods=["POST"])
def fetch_roster():
    request_args = request.get_json(silent=True)
    if request_args is None:
        return {"success": False, "reason": "Invalid JSON data"}
    if "url" not in request_args:
        return {"success": False, "reason": 'Missing "url" key in JSON data'}
    url = request_args["url"]

    error_msg, roster = fetch_roster_data.fetch(url)
    if error_msg is not None:
        return {"success": False, "reason": error_msg}

    # TODO: validate the roster
    # TODO: process the roster before saving it

    # use flash so that the url and last fetched time are updated
    flash("Success", "info")
    return {"success": True, "roster": roster}
