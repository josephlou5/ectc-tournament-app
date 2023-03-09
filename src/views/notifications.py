"""
The "notifications" view, which includes fetching the roster, fetching
team info, and sending notifications.
"""

# =============================================================================

import json
from pathlib import Path

from flask import flash, request

import db
from utils import fetch_roster_data
from utils.routes import AppRoutes, _render

# =============================================================================

app = AppRoutes()

STATIC_FOLDER = Path(__file__).parent / ".." / "static"
FETCH_ROSTER_LOGS_FILE = (STATIC_FOLDER / "fetch_roster_logs.json").resolve()

# =============================================================================


def get_last_fetched_time_str():
    last_fetched_dt = db.global_state.get_last_fetched_time()
    if last_fetched_dt is None:
        return None
    return last_fetched_dt.strftime("%Y-%m-%d %H:%M:%S")


@app.route("/notifications", methods=["GET"])
def notifications():
    spreadsheet_url = db.global_state.get_last_fetched_spreadsheet_url()
    last_fetched_time = get_last_fetched_time_str()
    has_fetch_logs = FETCH_ROSTER_LOGS_FILE.exists()
    return _render(
        "notifications/index.jinja",
        roster_worksheet_name=fetch_roster_data.ROSTER_WORKSHEET_NAME,
        spreadsheet_url=spreadsheet_url,
        last_fetched_time=last_fetched_time,
        has_fetch_logs=has_fetch_logs,
    )


@app.route("/notifications/fetch_roster", methods=["POST"])
def fetch_roster():
    request_args = request.get_json(silent=True)
    if request_args is None:
        return {"success": False, "reason": "Invalid JSON data"}
    if "url" not in request_args:
        return {"success": False, "reason": 'Missing "url" key in JSON data'}
    url = request_args["url"]

    error_msg, logs, roster = fetch_roster_data.fetch(url)
    if error_msg is not None:
        return {"success": False, "reason": error_msg}

    # TODO: save the roster

    # save the logs in a file
    full_logs = {
        "time_fetched": get_last_fetched_time_str(),
        "logs": logs,
    }
    FETCH_ROSTER_LOGS_FILE.write_text(
        json.dumps(full_logs, indent=2), encoding="utf-8"
    )

    # use flash so that the url and last fetched time are updated
    flash("Success", "info")
    return {"success": True, "roster": roster}


@app.route("/notifications/fetch_roster_logs", methods=["GET"])
def fetch_roster_logs():
    time_fetched = None
    logs = None
    if FETCH_ROSTER_LOGS_FILE.exists():
        try:
            full_logs = json.loads(FETCH_ROSTER_LOGS_FILE.read_bytes())
            time_fetched = full_logs["time_fetched"]
            logs = full_logs["logs"]
        except (json.decoder.JSONDecodeError, KeyError):
            # delete the file; it's faulty somehow
            FETCH_ROSTER_LOGS_FILE.unlink()
    return _render(
        "notifications/fetch_roster_logs.jinja",
        fetch_logs_filename=FETCH_ROSTER_LOGS_FILE.name,
        time_fetched=time_fetched,
        logs=logs,
    )
