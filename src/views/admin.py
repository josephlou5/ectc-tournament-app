"""
Views for an admin that are not the Admin Settings or Notifications
pages.
"""

# =============================================================================

import json

from flask import flash, request

import db
import utils
from utils import fetch_tms, mailchimp_utils, notifications_utils
from utils.auth import login_required
from utils.server import AppRoutes, _render, print_records, unsuccessful

# =============================================================================

app = AppRoutes()

# =============================================================================

# To prevent server timeouts, set a limit on the number of new contacts
# that can be added during a single roster fetch.
# This number was chosen arbitrarily; I'm not sure if it's good or bad.
NEW_CONTACTS_LIMIT = 200

# =============================================================================


def _edit_mailchimp_contacts(emails):
    """Adds the given user emails to Mailchimp.

    If there are Mailchimp errors, the errors themselves will be
    returned, which may be a bit too detailed for actual end users. This
    could be improved in the future for clearer error messages.

    Returns:
        Union[
            Tuple[str, None, None],
            Tuple[None, Optional[str], Set[str]]
        ]:
            An abort message, or a fetch error message and a set of the
            invalid emails that were added.
    """

    def _error(msg, invalid=None):
        if invalid is None:
            invalid = set()
        return None, msg, invalid

    print(" ", "Adding contacts to Mailchimp")

    if not db.global_state.has_mailchimp_api_key():
        return _error("No Mailchimp API key to import contacts")

    audience_id = db.global_state.get_mailchimp_audience_id()
    if audience_id is None:
        return _error("No selected Mailchimp audience id")

    error_msg, add_emails = mailchimp_utils.find_missing_members(
        audience_id, list(emails)
    )
    if error_msg is not None:
        return _error(error_msg)

    over_contacts_limit = len(add_emails) > NEW_CONTACTS_LIMIT
    print(
        " ",
        " ",
        f"{len(add_emails)} new contacts to add",
        "(over limit)" if over_contacts_limit else "",
    )

    if over_contacts_limit:
        abort_msg = (
            "Too many new contacts to add. "
            "Please see the fetch help page for a workaround."
        )
        return abort_msg, None, None

    invalid_emails = set()
    if len(add_emails) > 0:
        error_msg, invalid_emails = mailchimp_utils.add_members(
            audience_id, add_emails
        )
        if error_msg is not None:
            return _error(error_msg)
        print(" ", " ", f"{len(invalid_emails)} invalid emails found")

    tournament_tag = db.global_state.get_mailchimp_audience_tag()
    if tournament_tag is None:
        print(" ", " ", "No audience tag found in database")
    else:
        error_msg, tournament_tag_id = mailchimp_utils.get_or_create_segment(
            audience_id, tournament_tag
        )
        if error_msg is not None:
            return _error(error_msg, invalid_emails)

        tag_emails = set(emails) - invalid_emails
        print(
            " ",
            " ",
            f"Tagging all {len(tag_emails)} valid contacts with:",
            tournament_tag,
        )
        error_msg = mailchimp_utils.update_segment_emails(
            audience_id, tournament_tag_id, tag_emails
        )
        if error_msg is not None:
            return _error(error_msg, invalid_emails)

    return None, None, invalid_emails


@app.route("/fetch_roster", methods=["POST", "DELETE"])
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

    # add contacts to mailchimp and tag/untag them
    users_by_email = {user["email"]: user for user in roster["users"]}
    abort_msg, error_msg, invalid_emails = _edit_mailchimp_contacts(
        users_by_email.keys()
    )
    if abort_msg is not None:
        return unsuccessful(abort_msg)
    if error_msg is not None:
        error_messages.append(error_msg)
        logs.append({"level": "ERROR", "row_num": None, "message": error_msg})
        if flash_all:
            flash(error_msg, "fetch-roster.danger")

    all_emails_invalid = False
    if len(invalid_emails) == 0:
        pass
    elif len(invalid_emails) == len(users_by_email):
        # all emails were invalid
        all_emails_invalid = True
        error_msg = "All emails are invalid"
        error_messages.append(error_msg)
        logs.append({"level": "ERROR", "row_num": None, "message": error_msg})
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
            # probably won't happen due to validation/constraint errors,
            # since `fetch_roster()` should have good enough checks
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
        "time_fetched": utils.dt_str(
            db.global_state.get_roster_last_fetched_time()
        ),
        "logs": logs,
    }
    notifications_utils.FETCH_ROSTER_LOGS_FILE.write_text(
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


@app.route("/fetch_roster/logs", methods=["GET"])
@login_required(admin=True)
def view_fetch_roster_logs():
    logs_file = notifications_utils.FETCH_ROSTER_LOGS_FILE

    time_fetched = None
    logs = None
    has_errors = False
    has_warnings = False
    if logs_file.exists():
        try:
            full_logs = json.loads(logs_file.read_bytes())
            time_fetched = full_logs["time_fetched"]
            logs = full_logs["logs"]

            for log in logs:
                if log["level"] == "ERROR":
                    has_errors = True
                elif log["level"] == "WARNING":
                    has_warnings = True
                if has_errors and has_warnings:
                    break
        except (json.decoder.JSONDecodeError, KeyError):
            # delete the file; it's faulty somehow
            logs_file.unlink()

    warning_log_levels = []
    if has_errors:
        warning_log_levels.append("Error")
    if has_warnings:
        warning_log_levels.append("Warning")

    return _render(
        "notifications/fetch_roster_logs.jinja",
        # for a link to the raw logs file
        fetch_logs_filename=logs_file.name,
        time_fetched=time_fetched,
        logs=logs,
        warning_log_levels=warning_log_levels,
    )


@app.route("/full_roster", methods=["GET"])
@login_required(admin=True)
def view_full_roster():
    full_roster = db.roster.get_full_roster()
    has_fetch_logs = notifications_utils.has_fetch_roster_logs()

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
    divisions = set()
    for team in full_roster.pop("teams"):
        school_name = team.school.name
        if school_name not in teams:
            teams[school_name] = []
        teams[school_name].append(team)
        divisions.add(team.division)
    full_roster["teams_by_school"] = {
        school: sorted(team_list, key=fetch_tms.team_sort_key)
        for school, team_list in sorted(teams.items())
    }
    full_roster["divisions"] = sorted(
        divisions, key=fetch_tms.division_sort_key
    )

    is_roster_empty = all(len(objs) == 0 for objs in full_roster.values())

    return _render(
        "notifications/full_roster.jinja",
        **full_roster,
        is_roster_empty=is_roster_empty,
        has_fetch_logs=has_fetch_logs,
    )


@app.route("/full_roster/raw", methods=["GET"])
@login_required(admin=True)
def view_full_roster_raw():
    return db.roster.get_full_roster(as_json=True)


# =============================================================================


@app.route("/sent_emails", methods=["GET"])
@login_required(admin=True)
def view_sent_emails():
    sent_emails = db.sent_emails.get_all_sent_emails()
    return _render("/admin/sent_emails.jinja", sent_emails=sent_emails)
