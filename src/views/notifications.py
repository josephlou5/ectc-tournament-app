"""
The "notifications" view, which includes fetching the roster, fetching
team info, and sending notifications.
"""

# =============================================================================

import json
from pathlib import Path

from flask import flash

import db
from utils import fetch_tms
from utils.routes import AppRoutes, _render

# =============================================================================

app = AppRoutes()

STATIC_FOLDER = (Path(__file__).parent / ".." / "static").resolve()
FETCH_ROSTER_LOGS_FILE = STATIC_FOLDER / "fetch_roster_logs.json"

# =============================================================================


def get_roster_last_fetched_time_str():
    last_fetched_dt = db.global_state.get_roster_last_fetched_time()
    if last_fetched_dt is None:
        return None
    return last_fetched_dt.strftime("%Y-%m-%d %H:%M:%S")


@app.route("/notifications", methods=["GET"])
def notifications():
    roster_last_fetched_time = get_roster_last_fetched_time_str()
    has_fetch_logs = FETCH_ROSTER_LOGS_FILE.exists()
    return _render(
        "notifications/index.jinja",
        roster_worksheet_name=fetch_tms.ROSTER_WORKSHEET_NAME,
        roster_last_fetched_time=roster_last_fetched_time,
        has_fetch_logs=has_fetch_logs,
    )


@app.route("/notifications/fetch_roster", methods=["POST"])
def fetch_roster():
    print(" ", "Fetching teams roster from TMS spreadsheet")
    error_msg, logs, roster = fetch_tms.fetch_roster()
    if error_msg is not None:
        print(" ", "Failed:", error_msg)
        return {"success": False, "reason": error_msg}

    # TODO: save in database
    success = True

    # save the logs in a file
    full_logs = {
        "time_fetched": get_roster_last_fetched_time_str(),
        "logs": logs,
    }
    FETCH_ROSTER_LOGS_FILE.write_text(
        json.dumps(full_logs, indent=2), encoding="utf-8"
    )

    # print for server logs
    print(" ", "Time finished fetching:", full_logs["time_fetched"])
    headers = {"level": "Level", "row_num": "Row Num", "message": "Message"}
    col_widths = [len(h) for h in headers.values()]
    rows = []
    for log in logs:
        row = [str(log[key]) for key in headers]
        rows.append(row)
        for i in range(len(headers)):
            col_widths[i] = max(col_widths[i], len(row[i]))

    def print_row(values, spaces=2):
        if isinstance(values, list):
            segments = []
            for value, width in zip(values, col_widths):
                if value == "":
                    segments.append(" " * width)
                    continue
                segments.append(value.ljust(width))
        elif values == "":
            segments = [" " * width for width in col_widths]
        else:
            segments = [
                (values * int(width / len(values)))[:width]
                for width in col_widths
            ]
        print(" ", (" " * spaces).join(segments))

    print_row(list(headers.values()))
    print_row("-")
    for row in rows:
        print_row(row)

    if not success:
        return {"success": False, "reason": "Database error"}

    # use flash so the last fetched time is updated
    flash("Success", "fetch-roster")
    return {"success": True, "roster": roster}


@app.route("/notifications/fetch_roster/logs", methods=["GET"])
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
        # for a link to the raw logs file
        fetch_logs_filename=FETCH_ROSTER_LOGS_FILE.name,
        time_fetched=time_fetched,
        logs=logs,
    )
