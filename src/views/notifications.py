"""
The "notifications" view, which includes fetching the roster, fetching
team info, and sending notifications.
"""

# =============================================================================

import json
from pathlib import Path

from flask import flash, request

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

    # save in database
    print(" ", "Saving the roster to the database")
    success = db.roster.set_roster(roster)
    if success:
        logs.append(
            {
                "level": "INFO",
                "row_num": None,
                "message": "Saved roster in database",
            }
        )
    else:
        # probably won't happen, since `fetch_roster()` should have good
        # enough checks
        logs.append(
            {"level": "ERROR", "row_num": None, "message": "Database error"}
        )

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


@app.route("/notifications/full_roster", methods=["GET"])
def view_full_roster():
    full_roster = db.roster.get_full_roster()

    # split the users into coaches, athletes, and spectators
    coaches = []
    athletes = []
    spectators = []
    users = full_roster.pop("users")
    for user in users:
        if user.role == "COACH":
            coaches.append(user)
        elif user.role == "ATHLETE":
            athletes.append(user)
        elif user.role == "SPECTATOR":
            spectators.append(user)

    def sort_by_school(users):
        return sorted(users, key=lambda user: user.school_id)

    full_roster["coaches"] = sort_by_school(coaches)
    full_roster["athletes"] = sort_by_school(athletes)
    full_roster["spectators"] = sort_by_school(spectators)

    return _render("notifications/full_roster.jinja", **full_roster)


@app.route("/notifications/full_roster/raw", methods=["GET"])
def view_full_roster_raw():
    return db.roster.get_full_roster(as_json=True)


def _parse_matches_query(matches_query):
    """Handwritten parser to parse a match list str, with spaces or
    commas separating match groups, and with dashes representing match
    ranges.

    The parser is pretty forgiving; it allows numbers starting with 0s
    and has no restrictions on the value ranges. However, the end of
    ranges must be at least as large as the start of the range. Also,
    there is a cutoff on the number of matches that can be specified.
    """
    MAX_NUM_MATCHES = 50

    def _parse_error(msg, index=None):
        if index is not None:
            msg = f"Position {index+1}: {msg}"
        return msg, None

    # insertion-order collection of match numbers
    match_numbers = {}
    # a buffer of the last seen match number
    last_num = None
    # index of the seen dash
    saw_dash = None
    # the digits of the current number
    current_number = []

    def _add_number(i, c=None):
        nonlocal last_num, saw_dash

        if len(current_number) == 0:
            return None

        num_start_i = i - len(current_number)
        num = int("".join(current_number))
        current_number.clear()

        if saw_dash is not None:
            # end a range
            if num < last_num:
                return (
                    f"Position {num_start_i}: "
                    "Range end is smaller than range start"
                )
            if num == last_num:
                match_numbers[last_num] = True
            else:
                for x in range(last_num, num + 1):
                    match_numbers[x] = True
            last_num = None
            saw_dash = None
        else:
            # single match number
            if last_num is not None:
                match_numbers[last_num] = True
            last_num = num

        if len(match_numbers) > MAX_NUM_MATCHES:
            return f"Too many matches specified (max {MAX_NUM_MATCHES})"

        return None

    for i, c in enumerate(matches_query):
        if c.isspace() or c in (",", "-"):
            # end of a number
            error_msg = _add_number(i, c)
            if error_msg is not None:
                return _parse_error(error_msg)
            if c == ",":
                # explicitly start a new group (dashes cannot go across
                # commas)
                if saw_dash is not None:
                    return _parse_error(
                        f"Position {saw_dash+1}: Dash without end number"
                    )
                if last_num is not None:
                    match_numbers[last_num] = True
                last_num = None
            elif c == "-":
                if last_num is None:
                    return _parse_error(
                        f"Position {i+1}: Dash without a start number"
                    )
                if saw_dash is not None:
                    return _parse_error(f"Position {i+1}: invalid dash")
                saw_dash = i
            continue
        if c.isdigit():
            current_number.append(c)
            continue
        return _parse_error(f"Position {i+1}: unknown character: {c}")
    error_msg = _add_number(len(matches_query))
    if error_msg is not None:
        return _parse_error(error_msg)

    if saw_dash is not None:
        return _parse_error(f"Position {saw_dash+1}: Dash without end number")

    if last_num is not None:
        match_numbers[last_num] = True
    if len(match_numbers) > MAX_NUM_MATCHES:
        return _parse_error(
            f"Too many matches specified (max {MAX_NUM_MATCHES})"
        )

    return None, list(match_numbers.keys())


@app.route("/notifications/matches_info", methods=["GET"])
def fetch_matches_info():
    def _error(msg):
        return {"success": False, "reason": msg}

    matches_query = request.args.get("matches", None)
    if matches_query is None:
        return _error("No matches given.")
    matches_query = matches_query.strip()

    print(" ", "Fetching matches for query:", matches_query)

    error_msg, match_numbers = _parse_matches_query(matches_query)
    if error_msg is not None:
        print(" ", "Error parsing match query:", error_msg)
        return _error(error_msg)
    if len(match_numbers) == 0:
        print(" ", "Error: No match numbers given")
        return _error("No match numbers given.")
    match_numbers.sort()
    print(" ", "Parsed match numbers:", match_numbers)

    # TODO: fetch match info

    return {"success": True, "match_numbers": match_numbers}
