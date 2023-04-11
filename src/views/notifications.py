"""
The "notifications" view, which includes fetching the roster, fetching
team info, and sending notifications.
"""
# pylint: disable=too-many-lines

# =============================================================================

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from flask import flash, render_template, request

import db
import utils
from utils import fetch_tms, mailchimp_utils
from utils.auth import login_required, set_redirect_page
from utils.server import (
    AppRoutes,
    _render,
    get_request_json,
    print_records,
    unsuccessful,
)

# =============================================================================

app = AppRoutes()

STATIC_FOLDER = (Path(__file__).parent / ".." / "static").resolve()
FETCH_ROSTER_LOGS_FILE = STATIC_FOLDER / "fetch_roster_logs.json"

# Instead of injecting these characters into the Jinja template as a
# JavaScript RegExp object, the client-side JavaScript should be
# manually updated in `src/templates/notifications/index.jinja` whenever
# this value changes.
EMAIL_SUBJECT_VALID_CHARS = "-_+.,!#&()[]|:;'\"/?"
EMAIL_SUBJECT_VALID_CHARS_SET = set(EMAIL_SUBJECT_VALID_CHARS)

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

    global_state = db.global_state.get()
    last_matches_query = global_state.last_matches_query
    last_subject = global_state.mailchimp_subject
    send_to_coaches = global_state.send_to_coaches
    send_to_spectators = global_state.send_to_spectators
    send_to_subscribers = global_state.send_to_subscribers
    audience_tag = global_state.mailchimp_audience_tag
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
        send_to_coaches=send_to_coaches,
        send_to_spectators=send_to_spectators,
        send_to_subscribers=send_to_subscribers,
        EMAIL_SUBJECT_VALID_CHARS=EMAIL_SUBJECT_VALID_CHARS,
        audience_tag=audience_tag,
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

    # sort schools by name
    full_roster["schools"].sort(key=lambda s: s.name)

    # split the users into roles and schools
    coaches = {}
    athletes = {}
    spectators = {}
    for user in full_roster.pop("users"):
        school_name = user.school.name
        if user.role == "COACH":
            role_dict = coaches
        elif user.role == "ATHLETE":
            role_dict = athletes
        elif user.role == "SPECTATOR":
            role_dict = spectators
        else:
            # invalid role; shouldn't happen
            user_info = (
                f"{user.full_name} <{user.email}> ({user.role} at "
                f"{school_name})"
            )
            print(
                " ",
                f"Warning: got invalid role for user {user.id}:",
                user_info,
            )
            continue
        if school_name not in role_dict:
            role_dict[school_name] = []
        role_dict[school_name].append(user)

    def sort_users_dict(user_role_dict):
        return {
            school: sorted(
                user_list, key=lambda u: (u.last_name, u.first_name, u.email)
            )
            for school, user_list in sorted(user_role_dict.items())
        }

    full_roster["coaches"] = sort_users_dict(coaches)
    full_roster["athletes"] = sort_users_dict(athletes)
    full_roster["spectators"] = sort_users_dict(spectators)

    # organize teams by school
    teams = {}
    for team in full_roster.pop("teams"):
        school_name = team.school.name
        if school_name not in teams:
            teams[school_name] = []
        teams[school_name].append(team)
    full_roster["teams_by_school"] = {
        school: sorted(team_list, key=lambda t: t.code)
        for school, team_list in sorted(teams.items())
    }

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


@app.route("/mailchimp/templates", methods=["GET"])
@login_required(admin=True, save_redirect=False)
def get_mailchimp_templates():
    if not db.global_state.has_mailchimp_api_key():
        return unsuccessful("No Mailchimp API key")

    folder_id = db.global_state.get_mailchimp_folder_id()
    if folder_id is None:
        return unsuccessful("No selected Mailchimp template folder")

    print(" ", f"Fetching Mailchimp campaigns in folder {folder_id}")

    # fetch templates
    error_msg, templates = mailchimp_utils.get_campaigns_in_folder(folder_id)
    if error_msg is not None:
        return unsuccessful(
            error_msg, "Error while fetching Mailchimp campaigns"
        )

    if len(templates) == 0:
        print(" ", "Fetched 0 campaign templates")
        selected_template_id = None
    else:
        print(" ", "Fetched campaign templates:")
        print_records(templates[0].keys(), templates, indent=4, padding=2)

        # determine which template to select as default
        selected_template_id = db.global_state.get_mailchimp_template_id()
        if selected_template_id is None:
            print(" ", "No selected template in database")
        else:
            print(
                " ",
                "Selected template id from database:",
                selected_template_id,
            )
            for info in templates:
                if info["id"] == selected_template_id:
                    print(
                        " ",
                        " ",
                        f'Selected template: {info["title"]!r} ({info["id"]})',
                    )
                    break
            else:
                # invalid template id
                # clear from database (don't care if failed)
                _ = db.global_state.clear_mailchimp_template_id()
                selected_template_id = None
                print(
                    " ", " ", "Invalid selected template id (not in fetched)"
                )

    templates_html = render_template(
        "notifications/templates_info.jinja",
        templates=templates,
        selected_template_id=selected_template_id,
    )
    return {"success": True, "templates_html": templates_html}


def _validate_subject(subject, blast=False):
    """Validates a given subject with optional placeholder values.

    If `blast` is True, placeholders are not allowed. Otherwise,
    converts all placeholder names to lowercase.

    Returns:
        Union[Tuple[str, None], Tuple[None, str]]:
            An error message, or the validated subject.
    """
    VALID_PLACEHOLDERS = {
        "match",
        "division",
        "round",
        "blueteam",
        "redteam",
        "team",
    }

    def _error(msg):
        return msg, None

    subject_chars = []

    in_placeholder = False
    placeholder_chars = []
    has_match_number = False
    for i, c in enumerate(subject):
        if c == "{":
            if blast:
                return _error(
                    f"Index {i+1}: invalid open bracket: no placeholders in "
                    "blast email subject"
                )
            if in_placeholder:
                return _error(
                    f"Index {i+1}: invalid open bracket: cannot have a nested "
                    "placeholder"
                )
            in_placeholder = True
        elif c == "}":
            if blast:
                return _error(f"Index {i+1}: invalid character: {c}")
            if not in_placeholder:
                return _error(
                    f"Index {i+1}: invalid close bracket: not in a placeholder"
                )
            placeholder_str = "".join(placeholder_chars)
            bracket_index = i - len(placeholder_str)
            if placeholder_str == "":
                return _error(f"Index {bracket_index}: empty placeholder")
            if placeholder_str == "match":
                has_match_number = True
            elif placeholder_str not in VALID_PLACEHOLDERS:
                return _error(
                    f"Index {bracket_index}: unknown placeholder "
                    f'"{placeholder_str}"'
                )
            # reset placeholder values
            in_placeholder = False
            placeholder_chars.clear()
        elif in_placeholder:
            if not c.isalpha():
                return _error(
                    f"Index {i+1}: invalid character inside placeholder: {c}"
                )
            placeholder_chars.append(c.lower())
        elif not (
            c.isalpha()
            or c.isdigit()
            or c == " "
            or c in EMAIL_SUBJECT_VALID_CHARS_SET
        ):
            return _error(f"Index {i+1}: invalid character: {c}")

        if in_placeholder:
            subject_chars.append(c.lower())
        else:
            subject_chars.append(c)
    if in_placeholder:
        bracket_index = len(subject) - len(placeholder_chars)
        return _error(f"Index {bracket_index}: unclosed placeholder")
    if not blast and not has_match_number:
        return _error('Missing "{match}" placeholder')
    # valid!
    return None, "".join(subject_chars)


def _format_subject(subject, match_info):
    """Formats a subject with the possible placeholder values.

    Returns:
        Dict[str, str]: The subject for each team color in the format:
            'blue_team': subject
            'red_team': subject
        Note that the two subjects may be the same.
    """

    def _team_name(team_info):
        return " ".join(team_info["school_code"])

    blue_team = _team_name(match_info["blue_team"])
    red_team = _team_name(match_info["red_team"])
    kwargs = {
        "match": match_info["number"],
        "division": match_info["division"],
        "round": match_info["round"],
        "blueteam": blue_team,
        "redteam": red_team,
    }
    return {
        "blue_team": subject.format(**kwargs, team=blue_team),
        "red_team": subject.format(**kwargs, team=red_team),
    }


@app.route("/notifications/send", methods=["POST"])
@login_required(admin=True, save_redirect=False)
def send_notification():
    if not db.global_state.has_mailchimp_api_key():
        error_msg = "No Mailchimp API key"
        print(" ", "Error:", error_msg)
        return {"success": False, "errors": {"GENERAL": error_msg}}

    error_msg, request_args = get_request_json(
        "templateId",
        "subject",
        {"key": "blast", "type": bool, "required": False},
    )
    if error_msg is not None:
        return {"success": False, "errors": {"GENERAL": error_msg}}

    # get and validate request args
    template_id = request_args["templateId"].strip()
    subject = request_args["subject"].strip()
    if request_args.get("blast", False):
        blast = True
    else:
        blast = False
        error_msg, other_args = get_request_json(
            {"key": "sendToCoaches", "type": bool},
            {"key": "sendToSpectators", "type": bool},
            {"key": "sendToSubscribers", "type": bool},
            {"key": "matches", "type": list},
        )
        if error_msg is not None:
            return {"success": False, "errors": {"GENERAL": error_msg}}
        send_to_coaches = other_args["sendToCoaches"]
        send_to_spectators = other_args["sendToSpectators"]
        send_to_subscribers = other_args["sendToSubscribers"]
        matches = other_args["matches"]

    errors = {}

    if template_id == "":
        errors["TEMPLATE"] = "Template id is empty"
    if subject == "":
        errors["SUBJECT"] = "Subject is empty"
    else:
        error_msg, subject = _validate_subject(subject, blast)
        if error_msg is not None:
            errors["SUBJECT"] = error_msg

    # maps: severity -> match number -> statuses
    notification_status = defaultdict(
        lambda: defaultdict(
            lambda: {"warned_repeat_number": False, "messages": []}
        )
    )
    invalid_matches = {"index": [], "match_number": []}

    def _add_status(severity, match_number, message, repeat_number=False):
        match_status = notification_status[severity][match_number]
        if repeat_number:
            if match_status["warned_repeat_number"]:
                return
            match_status["warned_repeat_number"] = True
        match_status["messages"].append(message)

    # preprocess matches
    # maps: match number -> match info
    valid_matches = {}
    # set of (school, code) tuples
    all_team_names = set()
    if blast:
        # ignore matches
        pass
    elif len(matches) == 0:
        errors["GENERAL"] = "No matches given"
    else:
        # filter out valid matches
        def _check_valid_match(index, match_info):
            nonlocal notification_status, valid_matches, all_team_names

            match_number = match_info.get("number", None)
            if match_number is None:
                invalid_matches["index"].append(index)
                return

            for key in ("division", "round"):
                if key not in match_info:
                    invalid_matches["match_number"].append(match_number)
                    return
            if match_number in valid_matches:
                # repeated match number; assume same
                _add_status(
                    "WARNING",
                    match_number,
                    "Repeated match number",
                    repeat_number=True,
                )
                return

            for color in ("blue_team", "red_team"):
                if color not in match_info:
                    invalid_matches["match_number"].append(match_number)
                    return
                team_info = match_info[color]
                for key in ("school", "code"):
                    if key not in team_info:
                        invalid_matches["match_number"].append(match_number)
                        return
                team_info["school_code"] = (
                    team_info["school"],
                    team_info["code"],
                )
            if (
                match_info["blue_team"]["school_code"]
                == match_info["red_team"]["school_code"]
            ):
                # teams are the same; invalid match
                _add_status("ERROR", match_number, "Both teams are the same")
                return

            valid_matches[match_number] = match_info
            for color in ("blue_team", "red_team"):
                all_team_names.add(match_info[color]["school_code"])

        for i, match_info in enumerate(matches):
            _check_valid_match(i, match_info)
        if len(valid_matches) == 0:
            errors["GENERAL"] = "No valid matches given"
    if len(errors) > 0:
        print(" ", "Error with request args:")
        for key, msg in errors.items():
            print(" ", " ", f"{key}: {msg}")
        return {"success": False, "errors": errors}

    if blast:
        print(" ", "Sending blast notification email")
    else:
        print(" ", "Sending notification emails for matches")

    # get Mailchimp audience
    audience_id = db.global_state.get_mailchimp_audience_id()
    if audience_id is None:
        error_msg = "No selected Mailchimp audience"
        print(" ", "Error:", error_msg)
        return {"success": False, "errors": {"GENERAL": error_msg}}

    # validate template exists (but doesn't have to be in audience or
    # folder)
    error_msg, template_info = mailchimp_utils.get_campaign(template_id)
    if error_msg is not None:
        return {
            "success": False,
            "errors": {"TEMPLATE": "Invalid template id"},
        }
    mailchimp_template_name = template_info["title"]

    if blast:
        # get the audience tag
        audience_tag = db.global_state.get_mailchimp_audience_tag()
        if audience_tag is None:
            audience_tag_id = None
            recipients = "entire audience"
            print(" ", " ", "Sending to entire audience")
        else:
            recipients = f"tag {audience_tag!r}"
            print(" ", " ", "Sending to tag:", audience_tag)
            error_msg, audience_tag_id = mailchimp_utils.get_segment_id(
                audience_id, audience_tag
            )
            if error_msg is not None:
                print(
                    " ",
                    f"Error while getting segment {audience_tag!r}:",
                    error_msg,
                )
                return {
                    "success": False,
                    "errors": {"GENERAL": "Mailchimp error"},
                }
            if audience_tag_id is None:
                error_msg = (
                    f"Mailchimp audience tag {audience_tag!r} not found"
                )
                print(" ", "Error:", error_msg)
                return {"success": False, "errors": {"GENERAL": error_msg}}

        error_msg, campaign_info = mailchimp_utils.create_and_send_campaign(
            audience_id, template_id, subject, audience_tag_id
        )
        if error_msg is not None:
            print(" ", "Error while sending email:", error_msg)
            return {
                "success": False,
                "errors": {"GENERAL": "Email send failed"},
            }
        print(" ", " ", "Created campaign id:", campaign_info["id"])

        # save Mailchimp template and subject
        success = db.global_state.set_mailchimp_template_id(template_id)
        if not success:
            # it's okay if this fails
            print(" ", "Database error while saving Mailchimp template id")
        success = db.global_state.set_mailchimp_subject(subject)
        if not success:
            # it's okay if this fails
            print(" ", "Database error while saving Mailchimp subject")

        success_msg = f"Successfully sent blast notification to {recipients}"
        return {"success": True, "message": success_msg}

    # get TNS segment id
    error_msg, tns_segment_id = mailchimp_utils.get_or_create_tns_segment(
        audience_id
    )
    if error_msg is not None:
        print(" ", "Error while getting TNS segment:", error_msg)
        return {"success": False, "errors": {"GENERAL": "Mailchimp error"}}

    # get the team info for all the match teams
    print(" ", "Fetching info for all match teams")
    team_infos = db.roster.get_teams(list(all_team_names))

    # get the emails for each team and combine with match info
    print(" ", "Compiling match infos into emails to send")
    additional_recipient_roles = []
    if send_to_coaches:
        additional_recipient_roles.append("COACH")
    if send_to_spectators:
        additional_recipient_roles.append("SPECTATOR")

    if send_to_subscribers:
        teams_subscribers = db.subscriptions.get_subscribers(all_team_names)
    else:
        teams_subscribers = {}

    email_args = []
    for match_number, match_info in valid_matches.items():
        team_emails = {}
        missing_team = {}
        missing_emails = []
        for team_color in ("blue_team", "red_team"):
            color = team_color.split("_", 1)[0]
            team_info = match_info[team_color]

            school_team_code = team_info["school_code"]
            error_msg, team = team_infos[school_team_code]
            if error_msg is not None:
                # actual error message doesn't matter here, just that
                # there was an error
                missing_team[color] = school_team_code
                continue

            # just get the emails without any role information
            valid_emails = team.valid_emails()
            if len(valid_emails) == 0:
                missing_emails.append(color)
                continue

            # add other recipients
            school_name = team_info["school"]
            if len(additional_recipient_roles) > 0:
                valid_emails.extend(
                    db.roster.get_users_for_school(
                        school_name, additional_recipient_roles
                    )
                )
            # add subscribers
            valid_emails.extend(teams_subscribers.get(school_team_code, []))

            team_emails[team_color] = valid_emails
        if len(missing_team) > 0:
            team_names = " and ".join(
                f'{color} team {" ".join(school_code)!r}'
                for color, school_code in missing_team.items()
            )
            _add_status("ERROR", match_number, f"Could not find {team_names}")
            continue
        if len(missing_emails) == 2:
            # both teams don't have any valid emails
            _add_status(
                "ERROR", match_number, "No valid emails for both teams"
            )
            continue
        if len(missing_emails) == 1:
            color = missing_emails[0]
            _add_status(
                "ERROR", match_number, f"No valid emails for {color} team"
            )
            continue

        team_subjects = _format_subject(subject, match_info)
        if team_subjects["blue_team"] == team_subjects["red_team"]:
            # same subject, so can send one big email to all of them
            all_emails = list(
                set(team_emails["blue_team"] + team_emails["red_team"])
            )
            email_args.append(
                {
                    "match_number": match_number,
                    "description": f"Match {match_number}",
                    "subject": team_subjects["blue_team"],
                    "emails": all_emails,
                }
            )
        else:
            # send one email to each team
            for team_color in ("blue_team", "red_team"):
                color = team_color.split("_", 1)[0]
                email_args.append(
                    {
                        "match_number": match_number,
                        "description": f"Match {match_number}, {color} team",
                        "subject": team_subjects[team_color],
                        "emails": list(set(team_emails[team_color])),
                    }
                )

    if len(email_args) == 0:
        # all the teams were not found or invalid, so all matches were
        # also invalid
        print(
            " ", "Error: No generated emails, so no valid matches were given"
        )
        return {
            "success": False,
            "errors": {"GENERAL": "No valid matches given"},
        }

    # send emails
    print(" ", "Sending emails")
    emails_sent = []
    for args in email_args:
        print(" ", " ", f'Sending email for {args["description"]}:')
        print(" ", " ", " ", "Subject:", args["subject"])
        print(" ", " ", " ", "Recipients:", args["emails"])
        error_msg, _ = mailchimp_utils.create_and_send_match_campaign(
            audience_id,
            template_id,
            args["subject"],
            tns_segment_id,
            args["emails"],
        )
        if error_msg is not None:
            print(" ", " ", " ", "Error while sending email:", error_msg)
            _add_status("ERROR", args["description"], "Email send failed")
            continue
        emails_sent.append(
            {
                "match_number": args["match_number"],
                "subject": args["subject"],
                "recipients": args["emails"],
                "template_name": mailchimp_template_name,
                "time_sent": datetime.utcnow(),
            }
        )
    if len(emails_sent) == 0:
        error_msg = "All emails failed to send"
        print(" ", "Error:", error_msg)
        return {"success": False, "errors": {"GENERAL": error_msg}}

    # save Mailchimp template and subject
    success = db.global_state.set_mailchimp_template_id(template_id)
    if not success:
        # it's okay if this fails
        print(" ", "Database error while saving Mailchimp template id")
    success = db.global_state.set_mailchimp_subject(subject)
    if not success:
        # it's okay if this fails
        print(" ", "Database error while saving Mailchimp subject")
    # save other recipient settings
    success = db.global_state.set_other_recipients_settings(
        send_to_coaches=send_to_coaches,
        send_to_spectators=send_to_spectators,
        send_to_subscribers=send_to_subscribers,
    )
    if not success:
        # it's okay if this fails
        print(" ", "Database error while saving other recipient settings")

    # flash messages
    flash("Successfully sent match email notifications", "send-notif.success")
    for severity, matches_status in notification_status.items():
        lines = []
        if severity == "WARNING":
            for index in invalid_matches["index"]:
                lines.append(f"Invalid match info at index {index+1}")
            for match_number in invalid_matches["match_number"]:
                lines.append(f"Invalid match info for Match {match_number}")
        for match_number, match_status in matches_status.items():
            if isinstance(match_number, int):
                description = f"Match {match_number}"
            else:
                description = match_number
            for message in match_status["messages"]:
                lines.append(f"{description}: {message}")
        if len(lines) == 0:
            continue
        if len(lines) == 1:
            message = f"<strong>{severity.capitalize()}</strong>: {lines[0]}"
        else:
            message = "\n".join(
                [f"<strong>{severity.capitalize()}s</strong>:", *lines]
            )
        accent = severity
        if accent == "ERROR":
            accent = "danger"
        elif accent == "WARNING":
            accent = "warning"
        flash(message, f"send-notif.{accent}")

    success = db.match_status.add_emails_sent(emails_sent)
    if not success:
        error_msg = "Database error while saving sent emails"
        print(" ", "Error:", error_msg)
        flash(error_msg, "send-notif.danger")

    return {"success": True}


@app.route("/matches_status", methods=["GET"])
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
