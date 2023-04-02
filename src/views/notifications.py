"""
The "notifications" view, which includes fetching the roster, fetching
team info, and sending notifications.
"""

# =============================================================================

import json
from pathlib import Path

from flask import flash, render_template, request

import db
import utils
from utils import fetch_tms, mailchimp_utils
from utils.auth import login_required, set_redirect_page
from utils.server import AppRoutes, _render, print_records, unsuccessful

# =============================================================================

app = AppRoutes()

STATIC_FOLDER = (Path(__file__).parent / ".." / "static").resolve()
FETCH_ROSTER_LOGS_FILE = STATIC_FOLDER / "fetch_roster_logs.json"

# =============================================================================


def get_roster_last_fetched_time_str():
    last_fetched_dt = db.global_state.get_roster_last_fetched_time()
    return utils.dt_str(last_fetched_dt)


@app.route("/notifications", methods=["GET"])
@login_required(admin=True)
def notifications():
    # make sure the notifications page is ready to use
    has_all_admin_settings_error = db.global_state.has_all_admin_settings()

    roster_last_fetched_time = get_roster_last_fetched_time_str()
    has_fetch_logs = FETCH_ROSTER_LOGS_FILE.exists()
    last_matches_query = db.global_state.get_last_matches_query()
    last_subject = db.global_state.get_mailchimp_subject()
    return _render(
        "notifications/index.jinja",
        has_all_admin_settings_error=has_all_admin_settings_error,
        roster_worksheet_name=fetch_tms.ROSTER_WORKSHEET_NAME,
        possible_roles=[role.title() for role in fetch_tms.POSSIBLE_ROLES],
        possible_weights=[
            weight.title() for weight in fetch_tms.POSSIBLE_WEIGHT_CLASSES
        ],
        roster_last_fetched_time=roster_last_fetched_time,
        has_fetch_logs=has_fetch_logs,
        matches_worksheet_name=fetch_tms.MATCHES_WORKSHEET_NAME,
        last_matches_query=last_matches_query,
        last_subject=last_subject,
    )


@app.route("/notifications/fetch_roster", methods=["POST", "DELETE"])
@login_required(admin=True, save_redirect=False)
def fetch_roster():
    if request.method == "DELETE":
        print(" ", "Clearing full roster")
        all_success = True
        success = db.roster.clear_roster()
        if not success:
            all_success = False
            print(" ", "Database error while clearing roster tables")
        success = db.global_state.clear_roster_related_fields()
        if not success:
            all_success = False
            print(
                " ",
                (
                    "Database error while clearing roster related fields in "
                    "the global state"
                ),
            )
        if not all_success:
            flash("Database error", "fetch-roster.danger")
        else:
            success_msg = "Successfully cleared roster"
            print(" ", success_msg)
            flash(success_msg, "fetch-roster.success")
        return {"success": success}

    # If the query arg is given, flash all error messages as well. Note
    # that the value doesn't matter, so it could be "?flash_all=false"
    # and it would still work.
    flash_all = "flash_all" in request.args

    error_messages = []

    print(" ", "Fetching teams roster from TMS spreadsheet")
    error_msg, logs, roster = fetch_tms.fetch_roster()
    if error_msg is not None:
        if flash_all:
            flash(error_msg, "fetch-roster.danger")
        return unsuccessful(error_msg)

    logs_has_error = False
    logs_has_warning = False
    for log in logs:
        if log["level"] == "ERROR":
            logs_has_error = True
        elif log["level"] == "WARNING":
            logs_has_warning = True
        if logs_has_error and logs_has_warning:
            break

    # add contacts to mailchimp (also validates emails)
    print(" ", "Adding contacts to Mailchimp")
    all_emails_invalid = False
    if not db.global_state.has_mailchimp_api_key():
        error_msg = "No Mailchimp API key to import contacts"
        error_messages.append(error_msg)
        logs.append({"level": "ERROR", "row_num": None, "message": error_msg})
        if flash_all:
            flash(error_msg, "fetch-roster.danger")
    else:
        audience_id = db.global_state.get_mailchimp_audience_id()
        if audience_id is None:
            error_msg = "No selected Mailchimp audience id"
            error_messages.append(error_msg)
            logs.append(
                {"level": "ERROR", "row_num": None, "message": error_msg}
            )
            if flash_all:
                flash(error_msg, "fetch-roster.danger")
        else:
            deleted_emails = db.roster.get_all_user_emails(email_valid=True)
            users_by_email = {}
            for user in roster["users"]:
                email = user["email"]
                users_by_email[email] = user
                deleted_emails.discard(email)
            tournament_tag = db.global_state.get_mailchimp_audience_tag()
            error_msg, invalid_emails = mailchimp_utils.add_members(
                audience_id,
                list(users_by_email.keys()),
                tournament_tag=tournament_tag,
                remove_emails=deleted_emails,
            )

            if error_msg is not None:
                error_messages.append(error_msg)
                logs.append(
                    {"level": "ERROR", "row_num": None, "message": error_msg}
                )
                if flash_all:
                    flash(error_msg, "fetch-roster.danger")

            if len(invalid_emails) == 0:
                pass
            elif len(invalid_emails) == len(users_by_email):
                # all emails were invalid
                all_emails_invalid = True
                error_msg = "All emails are invalid"
                error_messages.append(error_msg)
                logs.append(
                    {"level": "ERROR", "row_num": None, "message": error_msg}
                )
                if flash_all:
                    flash(error_msg, "fetch-roster.danger")
            else:
                flash("There are some invalid emails", "fetch-roster.warning")
                for email in invalid_emails:
                    user = users_by_email[email]
                    user["email_valid"] = False
                    logs.append(
                        {
                            "level": "WARNING",
                            "row_num": user["row_num"],
                            "message": f"Invalid email: {email}",
                        }
                    )

    if not all_emails_invalid:
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
            # probably won't happen, since `fetch_roster()` should have
            # good enough checks
            error_msg = "Database error"
            error_messages.append(error_msg)
            logs.append(
                {"level": "ERROR", "row_num": None, "message": error_msg}
            )
            if flash_all:
                flash(error_msg, "fetch-roster.danger")

    # sort the logs by row number (`None` is at the end)
    logs.sort(
        key=lambda r: r["row_num"]
        if r["row_num"] is not None
        else float("inf")
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
    print_records(
        {"level": "Level", "row_num": "Row Num", "message": "Message"},
        logs,
        indent=2,
        padding=2,
    )

    if len(error_messages) > 0:
        return {"success": False, "reason": "; ".join(error_messages)}

    # use flash so the last fetched time is updated
    success_msg = "Successfully fetched roster"
    print(" ", success_msg)
    flash(success_msg, "fetch-roster.success")

    if logs_has_error:
        flash("There are some errors in the logs", "fetch-roster.warning")
    elif logs_has_warning:
        flash("There are some warnings in the logs", "fetch-roster.warning")

    return {"success": True}


@app.route("/notifications/fetch_roster/logs", methods=["GET"])
@login_required(admin=True)
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
@login_required(admin=True)
def view_full_roster():
    full_roster = db.roster.get_full_roster()
    has_fetch_logs = FETCH_ROSTER_LOGS_FILE.exists()

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
    full_roster["is_roster_empty"] = all(
        len(objs) == 0 for objs in full_roster.values()
    )

    return _render(
        "notifications/full_roster.jinja",
        **full_roster,
        has_fetch_logs=has_fetch_logs,
    )


@app.route("/notifications/full_roster/raw", methods=["GET"])
@login_required(admin=True)
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


def _clean_matches_query(match_numbers):
    """Returns a "clean" version of a matches query string that
    represents the specified match numbers.
    """
    groups = []
    group_start = None
    group_end = None

    def add_group():
        if group_start == group_end:
            groups.append(str(group_start))
        else:
            groups.append(f"{group_start}-{group_end}")

    # find all consecutive groups
    for num in sorted(set(match_numbers), key=fetch_tms.match_number_sort_key):
        if group_start is not None:
            # has to be in the same hundred
            if (num // 100 == group_end // 100) and num == group_end + 1:
                group_end = num
                continue
            add_group()
        group_start = num
        group_end = num
    if group_start is not None:
        add_group()
    return ",".join(groups)


@app.route("/notifications/matches_info", methods=["GET"])
@login_required(admin=True, save_redirect=False)
def fetch_matches_info():
    """Fetches the info for the given matches query from the "matches"
    query arg.

    Also accepts the "previous" query arg, which is another matches
    query with the current matches. Both queries will be combined and
    all combined matches will be fetched and returned.
    """

    matches_query = request.args.get("matches", None)
    if matches_query is None:
        return unsuccessful("No matches query given")
    matches_query = matches_query.strip()
    if matches_query == "":
        return unsuccessful("No matches query given")
    previous_matches_query = request.args.get("previous", "")

    print(" ", "Fetching matches for query:", matches_query)
    print(" ", "Previous matches:", previous_matches_query)

    error_msg, match_numbers = _parse_matches_query(matches_query)
    if error_msg is not None:
        return unsuccessful(error_msg, "Error parsing matches query")
    if len(match_numbers) == 0:
        return unsuccessful("No match numbers given")
    match_numbers.sort(key=fetch_tms.match_number_sort_key)
    print(" ", "Parsed match numbers:", match_numbers)

    error_msg, previous_match_numbers = _parse_matches_query(
        previous_matches_query
    )
    if error_msg is not None:
        print(" ", "Error parsing previous matches query:", error_msg)
    else:
        match_numbers.extend(previous_match_numbers)
        match_numbers.sort(key=fetch_tms.match_number_sort_key)
        print(" ", " ", "With previous match numbers:", match_numbers)

    warnings = []

    # fetch info for all the matches
    print(" ", "Fetching match info from TMS")
    # if no matches found in TMS, returns error
    error_msg, match_teams = fetch_tms.fetch_match_teams(match_numbers)
    if error_msg is not None:
        print(" ", "Error:", error_msg)
        return {
            "success": False,
            "reason": f"Error in spreadsheet: {error_msg}",
        }

    # get the team info for all the match teams
    print(" ", "Fetching info for all match teams")
    # maps: match number -> team code
    match_same_teams = {}
    # maps: (school, code) -> list of match numbers
    all_team_infos = {}
    for match_team in match_teams:
        match_number = match_team["number"]
        if not match_team["found"]:
            warnings.append(f"Match {match_number} not found")
            continue
        team_code = match_team["blue_team"].get("school_code", None)
        has_same_team = team_code == match_team["red_team"].get(
            "school_code", None
        )
        if team_code is not None and has_same_team:
            match_same_teams[match_number] = team_code
            if team_code not in all_team_infos:
                all_team_infos[team_code] = []
            all_team_infos[team_code].append(match_number)
            continue
        for color in ("blue_team", "red_team"):
            team_info = match_team[color]
            if not team_info["valid"]:
                continue
            school_team_code = team_info["school_code"]
            if school_team_code not in all_team_infos:
                all_team_infos[school_team_code] = []
            all_team_infos[school_team_code].append(match_number)
    # check if some matches have the same teams
    for match_number, (school, team_code) in match_same_teams.items():
        warnings.append(
            f'Match {match_number} has team "{school} {team_code}" '
            "for both blue and red"
        )
    # check if some teams have multiple matches
    for (school, team_code), team_matches in all_team_infos.items():
        if len(team_matches) <= 1:
            continue
        matches_list_str = ", ".join(map(str, team_matches))
        warnings.append(
            f'Matches {matches_list_str} all have team "{school} {team_code}"'
        )

    # get the actual team infos from the database
    team_infos = db.roster.get_teams(list(all_team_infos.keys()))

    # combine the team info into match info
    if len(all_team_infos) == 0:
        print(" ", "No valid teams found")
    else:
        print(" ", "Compiling match infos")
    matches = []
    for match_team in match_teams:
        match_number = match_team["number"]
        if not match_team["found"]:
            continue

        match_valid = True
        match_invalid_msg = None

        def _invalid_match(msg):
            nonlocal match_valid, match_invalid_msg
            match_valid = False
            if match_invalid_msg is None:
                match_invalid_msg = msg

        if match_number in match_same_teams:
            # blue and red teams are the same
            _invalid_match("Teams are the same")

        match_info = {"number": match_number}
        missing_keys = []
        for key in ("division", "round"):
            value = match_team[key]
            if value == "":
                missing_keys.append(key.capitalize())
            match_info[key] = value

        compact_info = dict(match_info)

        # add match status (doesn't need to be in compact info)
        match_status = match_team["status"]
        if match_status == "":
            missing_keys.append("Status")
        match_info["status"] = match_status

        if len(missing_keys) > 0:
            missing_str = ", ".join(missing_keys)
            _invalid_match(f"Missing {missing_str}")

        invalid_teams = []
        invalid_team_emails = []
        for color in ("blue_team", "red_team"):
            team_color = color.split("_", 1)[0].capitalize()
            team_info = match_team[color]
            if not team_info["valid"]:
                invalid_teams.append(team_color)
                match_info[color] = {
                    "valid": False,
                    "name": team_info["name"],
                }
                continue
            error_msg, team = team_infos[team_info["school_code"]]
            if error_msg is not None:
                invalid_teams.append(team_color)
                match_info[color] = {
                    "valid": False,
                    "name": team_info["name"],
                    "error": error_msg,
                }
                continue
            match_info[color] = {
                "valid": True,
                "name": team.school_code,
                "team": team,
            }
            compact_info[color] = {
                "school": team.school.name,
                "code": team.code,
            }
            team_has_valid_email = False
            for weight in ("light", "middle", "heavy"):
                user = getattr(team, weight)
                if user is not None and user.email_valid:
                    team_has_valid_email = True
                    break
            else:
                for user in team.alternates:
                    if user.email_valid:
                        team_has_valid_email = True
                        break
            if not team_has_valid_email:
                # at least one person on the team must receive the email
                invalid_team_emails.append(team_color)

        if len(invalid_teams) == 0:
            pass
        elif len(invalid_teams) == 1:
            _invalid_match(f"{invalid_teams[0]} team invalid")
        else:  # len(invalid_teams) == 2
            _invalid_match("Both teams invalid")

        if len(invalid_team_emails) == 0:
            pass
        elif len(invalid_team_emails) == 1:
            _invalid_match(
                f"{invalid_team_emails[0]} team has no valid emails"
            )
        else:  # len(invalid_team_emails) == 2
            _invalid_match("No teams have valid emails")

        match_info["valid"] = match_valid
        match_info["invalid_msg"] = match_invalid_msg

        if match_valid:
            match_info["compact"] = utils.json_dump_compact(compact_info)
        else:
            match_info["compact"] = utils.json_dump_compact(
                {"number": match_number}
            )

        matches.append(match_info)

    # only include the found matches
    clean_matches_query = _clean_matches_query(
        match_info["number"] for match_info in matches
    )
    # save the "clean" last matches query (don't care if failed)
    _ = db.global_state.set_last_matches_query(clean_matches_query)

    if len(matches) == 0:
        matches_rows_html = None
    else:
        matches_rows_html = render_template(
            "notifications/matches_info_rows.jinja",
            matches=matches,
            status_accents=fetch_tms.MATCH_STATUS_TABLE_ACCENTS,
        )
    return {
        "success": True,
        "last_matches_query": clean_matches_query,
        "matches_rows_html": matches_rows_html,
        "warnings": warnings,
    }


@app.route("/notifications/matches_info/query", methods=["GET"])
@login_required(admin=True, save_redirect=False)
def get_matches_query():
    """Gets the clean matches query for the given matches."""

    matches_query = request.args.get("matches", None)
    if matches_query is None:
        return unsuccessful("No matches query given")
    matches_query = matches_query.strip()
    if matches_query == "":
        return unsuccessful("No matches query given")

    error_msg, match_numbers = _parse_matches_query(matches_query)
    if error_msg is not None:
        return unsuccessful(error_msg, "Error parsing matches query:")
    match_numbers.sort(key=fetch_tms.match_number_sort_key)

    clean_matches_query = _clean_matches_query(match_numbers)
    # save the "clean" last matches query (don't care if failed)
    _ = db.global_state.set_last_matches_query(clean_matches_query)

    return {"success": True, "matches_query": clean_matches_query}


@app.route("/notifications/matches_status", methods=["GET"])
def view_matches_status():
    set_redirect_page()

    matches_statuses = db.match_status.get_matches_status()

    # sort by match number
    hundreds = []
    ordered_statuses = []
    last_hundred = None
    for match_number, match_status in sorted(
        matches_statuses.items(),
        key=lambda pair: fetch_tms.match_number_sort_key(pair[0]),
    ):
        match_number_hundred = match_number // 100
        hundred_str = f"{match_number_hundred}00"
        if last_hundred is None or match_number_hundred != last_hundred:
            last_hundred = match_number_hundred
            hundreds.append(hundred_str)
        match_status["hundred_str"] = hundred_str
        ordered_statuses.append(match_status)

    return _render(
        "/notifications/matches_status.jinja",
        hundreds=hundreds,
        statuses=ordered_statuses,
        status_accents=fetch_tms.MATCH_STATUS_TABLE_ACCENTS,
    )
