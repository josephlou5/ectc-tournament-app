"""
The "notifications" view, which includes fetching the roster, fetching
team info, and sending notifications.
"""

# =============================================================================

from collections import defaultdict
from datetime import datetime

from flask import flash, render_template, request

import db
import utils
from utils import fetch_tms, mailchimp_utils
from utils import notifications_utils as helpers
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


@app.route("/notifications", methods=["GET"])
@login_required(admin=True)
def notifications():
    roster_last_fetched_time = utils.dt_str(
        db.global_state.get_roster_last_fetched_time()
    )
    has_fetch_logs = helpers.has_fetch_roster_logs()

    # make sure the notifications page / section is ready to use
    has_all_admin_settings_error = db.global_state.has_all_admin_settings()
    notifications_page_enabled = has_all_admin_settings_error is None
    send_notifications_section_enabled = (
        notifications_page_enabled and roster_last_fetched_time is not None
    )

    global_state = db.global_state.get()
    last_matches_query = global_state.last_matches_query
    last_match_subject = global_state.mailchimp_match_subject
    last_blast_subject = global_state.mailchimp_blast_subject
    send_to_coaches = global_state.send_to_coaches
    send_to_spectators = global_state.send_to_spectators
    send_to_subscribers = global_state.send_to_subscribers
    audience_tag = global_state.mailchimp_audience_tag

    divisions = db.roster.get_all_divisions()
    division_groups = fetch_tms.split_divisions_by_groups(divisions)

    return _render(
        "notifications/index.jinja",
        has_all_admin_settings_error=has_all_admin_settings_error,
        notifications_page_enabled=notifications_page_enabled,
        send_notifications_section_enabled=send_notifications_section_enabled,
        roster_worksheet_name=fetch_tms.ROSTER_WORKSHEET_NAME,
        possible_roles=[role.title() for role in fetch_tms.POSSIBLE_ROLES],
        possible_weights=[
            weight.title() for weight in fetch_tms.POSSIBLE_WEIGHT_CLASSES
        ],
        roster_last_fetched_time=roster_last_fetched_time,
        has_fetch_logs=has_fetch_logs,
        matches_worksheet_name=fetch_tms.MATCHES_WORKSHEET_NAME,
        last_matches_query=last_matches_query,
        last_match_subject=last_match_subject,
        last_blast_subject=last_blast_subject,
        send_to_coaches=send_to_coaches,
        send_to_spectators=send_to_spectators,
        send_to_subscribers=send_to_subscribers,
        EMAIL_SUBJECT_VALID_CHARS=helpers.EMAIL_SUBJECT_VALID_CHARS,
        audience_tag=audience_tag,
        no_divisions=len(divisions) == 0,
        division_groups=division_groups,
    )


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

    error_msg, match_numbers = helpers.parse_matches_query(matches_query)
    if error_msg is not None:
        return unsuccessful(error_msg, "Error parsing matches query")
    if len(match_numbers) == 0:
        return unsuccessful("No match numbers given")
    match_numbers.sort(key=fetch_tms.match_number_sort_key)
    print(" ", "Parsed match numbers:", match_numbers)

    (
        error_msg,
        previous_match_numbers,
    ) = helpers.parse_matches_query(previous_matches_query)
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
    # maps: (school, division, team number) -> set of match numbers
    all_team_matches = {}
    for match_team in match_teams:
        match_number = match_team["number"]
        if not match_team["found"]:
            warnings.append(f"Match {match_number} not found")
            continue
        school_team_codes = []
        for color in ("blue_team", "red_team"):
            team_info = match_team[color]
            if not team_info["valid"]:
                continue
            school_team_codes.append(team_info["school_team_code"])
        if (
            len(school_team_codes) == 2
            and school_team_codes[0] == school_team_codes[1]
        ):
            # same teams
            match_same_teams[match_number] = school_team_codes[0]
        for school_team_code in set(school_team_codes):
            if school_team_code not in all_team_matches:
                all_team_matches[school_team_code] = set()
            all_team_matches[school_team_code].add(match_number)
    # check if some matches have the same teams
    for match_number, school_team_code in match_same_teams.items():
        team_name = fetch_tms.school_team_code_to_str(*school_team_code)
        warnings.append(
            f"Match {match_number} has same blue and red team: {team_name}"
        )
    # check if some teams have multiple matches
    for school_team_code, team_matches in all_team_matches.items():
        if len(team_matches) <= 1:
            continue
        matches_list_str = utils.list_of_items(sorted(team_matches))
        warnings.append(
            f"Matches {matches_list_str} all have team "
            f"{fetch_tms.school_team_code_to_str(*school_team_code)!r}"
        )

    if len(all_team_matches) == 0:
        print(" ", "No valid teams found")
    else:
        print(" ", "Compiling match infos")

    # get the actual team infos from the database
    # maps: (school, division, team number) -> (error message, team obj)
    team_infos = db.roster.get_teams(list(all_team_matches.keys()))

    # combine the team info into match info
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

        match_division = match_info["division"] or None

        invalid_teams = []
        invalid_team_emails = []
        invalid_team_divisions = []
        for color in ("Blue", "Red"):
            team_color = f"{color.lower()}_team"
            team_info = match_team[team_color]
            if not team_info["valid"]:
                invalid_teams.append(color)
                match_info[team_color] = {
                    "valid": False,
                    "name": team_info["name"],
                }
                continue
            school_team_code = team_info["school_team_code"]
            _, team_division, _ = school_team_code
            error_msg, team = team_infos[school_team_code]
            if error_msg is not None:
                invalid_teams.append(color)
                match_info[team_color] = {
                    "valid": False,
                    "name": team_info["name"],
                    "error": error_msg,
                }
                continue

            match_info[team_color] = {
                "valid": True,
                "name": team.name,
                "team": team,
            }
            compact_info[team_color] = {
                "school": team.school.name,
                # don't need to include division because if valid it is
                # the same as the match division
                "number": team.number,
            }

            if len(team.valid_emails()) == 0:
                # at least one person on the team must receive the email
                invalid_team_emails.append(color)

            if team_division != match_division:
                invalid_team_divisions.append(color)

        for invalids, msg, both_msg in (
            (invalid_teams, "invalid", None),
            (
                invalid_team_emails,
                "has no valid emails",
                "No teams have valid emails",
            ),
            (invalid_team_divisions, "in wrong division", None),
        ):
            if len(invalids) == 0:
                continue
            if len(invalids) == 1:
                error_msg = f"{invalids[0]} team {msg}"
            else:  # len(invalids) == 2
                error_msg = both_msg or f"Both teams {msg}"
            _invalid_match(error_msg)

        match_info["valid"] = match_valid
        match_info["invalid_msg"] = match_invalid_msg

        if not match_valid:
            compact_info = {"number": match_number}
        match_info["compact"] = utils.json_dump_compact(compact_info)

        matches.append(match_info)

    # only include the found matches
    clean_matches_query = helpers.clean_matches_query(
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

    error_msg, match_numbers = helpers.parse_matches_query(matches_query)
    if error_msg is not None:
        return unsuccessful(error_msg, "Error parsing matches query:")
    match_numbers.sort(key=fetch_tms.match_number_sort_key)

    clean_matches_query = helpers.clean_matches_query(match_numbers)
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
        selected_match_template_id = None
        selected_blast_template_id = None
    else:
        print(" ", "Fetched campaign templates:")
        print_records(templates[0].keys(), templates, indent=4, padding=2)

        # maps: template id -> template info
        templates_by_id = {
            template_info["id"]: template_info for template_info in templates
        }

        # determine which templates to select as default
        selected_match_template_id = (
            mailchimp_utils.find_selected_from_database(
                templates_by_id,
                "match template",
                db.global_state.get_mailchimp_match_template_id,
                db.global_state.clear_mailchimp_match_template_id,
                "{title!r} ({id})",
            )
        )
        selected_blast_template_id = (
            mailchimp_utils.find_selected_from_database(
                templates_by_id,
                "blast template",
                db.global_state.get_mailchimp_blast_template_id,
                db.global_state.clear_mailchimp_blast_template_id,
                "{title!r} ({id})",
            )
        )

    match_templates_html = render_template(
        "notifications/templates_info.jinja",
        blast=False,
        templates=templates,
        selected_template_id=selected_match_template_id,
    )
    blast_templates_html = render_template(
        "notifications/templates_info.jinja",
        blast=True,
        templates=templates,
        selected_template_id=selected_blast_template_id,
    )
    return {
        "success": True,
        "match_templates_html": match_templates_html,
        "blast_templates_html": blast_templates_html,
    }


@app.route("/notifications/send/matches", methods=["POST"])
@login_required(admin=True, save_redirect=False)
def send_match_notification():
    if not db.global_state.has_mailchimp_api_key():
        return helpers.unsuccessful_notif("No Mailchimp API key")

    error_msg, request_args = get_request_json(
        "templateId",
        "subject",
        {"key": "matches", "type": list},
        {"key": "sendToCoaches", "type": bool},
        {"key": "sendToSpectators", "type": bool},
        {"key": "sendToSubscribers", "type": bool},
    )
    if error_msg is not None:
        return helpers.unsuccessful_notif(error_msg)

    # get and validate request args
    template_id = request_args["templateId"].strip()
    subject = request_args["subject"].strip()
    matches = request_args["matches"]
    send_to_coaches = request_args["sendToCoaches"]
    send_to_spectators = request_args["sendToSpectators"]
    send_to_subscribers = request_args["sendToSubscribers"]

    errors = {}

    if template_id == "":
        errors["TEMPLATE"] = "Template id is empty"
    if subject == "":
        errors["SUBJECT"] = "Subject is empty"
    else:
        error_msg, subject = helpers.validate_subject(subject)
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

    # filter out valid matches
    def _check_valid_match(index, match_info):
        match_number = match_info.get("number", None)
        if match_number is None:
            invalid_matches["index"].append(index)
            return

        for key in ("division", "round"):
            if key not in match_info:
                invalid_matches["match_number"].append(match_number)
                return
        match_division = match_info["division"]

        if match_number in valid_matches:
            # repeated match number; assume same
            _add_status(
                "WARNING",
                match_number,
                "Repeated match number",
                repeat_number=True,
            )
            return

        school_team_codes = set()
        for team_color in ("blue_team", "red_team"):
            if team_color not in match_info:
                invalid_matches["match_number"].append(match_number)
                return
            team_info = match_info[team_color]
            for key in ("school", "number"):
                if key not in team_info:
                    invalid_matches["match_number"].append(match_number)
                    return
            school_team_code = (
                team_info["school"],
                match_division,
                team_info["number"],
            )
            team_info["school_team_code"] = school_team_code
            school_team_codes.add(school_team_code)
        if len(school_team_codes) == 1:
            # teams are the same; invalid match
            _add_status("ERROR", match_number, "Both teams are the same")
            return

        valid_matches[match_number] = match_info
        all_team_names.update(school_team_codes)

    if len(matches) == 0:
        errors["GENERAL"] = "No matches given"
    else:
        for i, match_info in enumerate(matches):
            _check_valid_match(i, match_info)
        if len(valid_matches) == 0:
            errors["GENERAL"] = "No valid matches given"

    if len(errors) > 0:
        print(" ", "Error with request args:")
        for key, msg in errors.items():
            print(" ", " ", f"{key}: {msg}")
        return {"success": False, "errors": errors}

    print(" ", "Sending notification emails for matches")

    # get Mailchimp audience
    audience_id = db.global_state.get_mailchimp_audience_id()
    if audience_id is None:
        return helpers.unsuccessful_notif("No selected Mailchimp audience")

    # validate template exists (but doesn't have to be in audience or
    # folder)
    error_msg, template_info = mailchimp_utils.get_campaign(template_id)
    if error_msg is not None:
        return helpers.unsuccessful_notif(template="Invalid template id")
    mailchimp_template_name = template_info["title"]

    # get TNS segment id
    error_msg, tns_segment_id = mailchimp_utils.get_or_create_tns_segment(
        audience_id
    )
    if error_msg is not None:
        print(" ", "Error while getting TNS segment:", error_msg)
        return helpers.unsuccessful_notif("Mailchimp error", print_error=False)

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
        teams_subscribers = db.subscriptions.get_all_subscribers(
            all_team_names
        )
    else:
        teams_subscribers = {}

    email_args = []
    for match_number, match_info in valid_matches.items():
        # maps: team color -> list of emails
        team_emails = {}
        # maps: color -> name of missing team
        missing_team = {}
        # colors of the teams that are missing valid emails
        missing_emails = []
        for color in ("blue", "red"):
            team_color = f"{color}_team"
            team_info = match_info[team_color]

            school_team_code = team_info["school_team_code"]
            error_msg, team = team_infos[school_team_code]
            if error_msg is not None:
                # actual error message doesn't matter here, just that
                # there was an error
                missing_team[color] = fetch_tms.school_team_code_to_str(
                    *school_team_code
                )
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
                f"{color} team {team_name!r}"
                for color, team_name in missing_team.items()
            )
            _add_status("ERROR", match_number, f"Could not find {team_names}")
            continue
        if len(missing_emails) > 0:
            if len(missing_emails) == 1:
                color = missing_emails[0]
                error_msg = f"No valid emails for {color} team"
            else:  # len(missing_emails) == 2
                # both teams don't have any valid emails
                error_msg = "No valid emails for both teams"
            _add_status("ERROR", match_number, error_msg)
            continue

        team_subjects = helpers.format_team_subjects(subject, match_info)
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
            for color in ("blue", "red"):
                team_color = f"{color}_team"
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
        return helpers.unsuccessful_notif(
            "No valid matches given", print_error=False
        )

    # send emails
    print(" ", "Sending emails")
    emails_sent = []
    for args in email_args:
        print(" ", " ", f'Sending email for {args["description"]}:')
        print(" ", " ", " ", "Subject:", args["subject"])
        print(" ", " ", " ", "Recipients:", args["emails"])
        error_msg, _ = mailchimp_utils.create_and_send_campaign_to_emails(
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
                "template_name": mailchimp_template_name,
                "subject": args["subject"],
                "time_sent": datetime.utcnow(),
                "recipients": args["emails"],
            }
        )
    if len(emails_sent) == 0:
        return helpers.unsuccessful_notif("All emails failed to send")

    # save Mailchimp template and subject
    success = db.global_state.set_mailchimp_match_template_id(template_id)
    if not success:
        # it's okay if this fails
        print(" ", "Database error while saving Mailchimp template id")
    success = db.global_state.set_mailchimp_match_subject(subject)
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

    success = db.sent_emails.add_emails_sent(emails_sent)
    if not success:
        error_msg = "Database error while saving sent emails"
        print(" ", "Error:", error_msg)
        flash(error_msg, "send-notif.danger")

    return {"success": True}


@app.route("/notifications/send/blast", methods=["POST"])
@login_required(admin=True, save_redirect=False)
def send_blast_notification():
    # upon success, a message will be sent with the response instead of
    # flashed so that any potential matches queue is left intact

    if not db.global_state.has_mailchimp_api_key():
        return helpers.unsuccessful_notif("No Mailchimp API key")

    error_msg, request_args = get_request_json(
        "templateId",
        "subject",
        {"key": "tag", "required": False},
        {"key": "entireAudience", "type": bool, "required": False},
        {"key": "division", "required": False},
    )
    if error_msg is not None:
        return helpers.unsuccessful_notif(error_msg)

    # get and validate request args
    template_id = request_args["templateId"].strip()
    subject = request_args["subject"].strip()
    tag = request_args.get("tag", None)
    entire_audience = "entireAudience" in request_args
    division = request_args.get("division", None)

    errors = {}

    if template_id == "":
        errors["TEMPLATE"] = "Template id is empty"
    if subject == "":
        errors["SUBJECT"] = "Subject is empty"
    else:
        error_msg, subject = helpers.validate_subject(subject, blast=True)
        if error_msg is not None:
            errors["SUBJECT"] = error_msg
    if tag is not None:
        # send to the given tag
        entire_audience = False
        division = None
        if tag == "":
            errors["RECIPIENTS"] = "Tag is empty"
    elif entire_audience:
        # send to entire audience
        tag = None
        division = None
    elif division is not None:
        # send to the given division
        tag = None
        entire_audience = False
        if division == "":
            errors["RECIPIENTS"] = "Division is empty"
        else:
            division_emails = db.roster.get_emails_for_division(division)
            if len(division_emails) == 0:
                errors[
                    "RECIPIENTS"
                ] = "Selected division does not have any valid emails"
    else:
        errors["RECIPIENTS"] = "No recipients specified"

    if len(errors) > 0:
        print(" ", "Error with request args:")
        for key, msg in errors.items():
            print(" ", " ", f"{key}: {msg}")
        return {"success": False, "errors": errors}

    print(" ", "Sending blast notification email")

    # get Mailchimp audience
    audience_id = db.global_state.get_mailchimp_audience_id()
    if audience_id is None:
        return helpers.unsuccessful_notif("No selected Mailchimp audience")

    # validate template exists (but doesn't have to be in audience or
    # folder)
    error_msg, template_info = mailchimp_utils.get_campaign(template_id)
    if error_msg is not None:
        return helpers.unsuccessful_notif(template="Invalid template id")
    mailchimp_template_name = template_info["title"]

    email_sent_info = {
        "template_name": mailchimp_template_name,
        "subject": subject,
    }

    if tag is not None:
        recipients = f"tag {tag!r}"
        print(" ", " ", "Sending to tag:", tag)

        error_msg, tag_id = mailchimp_utils.get_segment_id(audience_id, tag)
        if error_msg is not None:
            print(" ", f"Error while getting segment {tag!r}:", error_msg)
            return helpers.unsuccessful_notif(
                "Mailchimp error", print_error=False
            )
        if tag_id is None:
            return helpers.unsuccessful_notif(
                f"Mailchimp tag {tag!r} not found"
            )

        email_sent_info["tag"] = tag

        # send email
        error_msg, campaign_info = mailchimp_utils.create_and_send_campaign(
            audience_id, template_id, subject, tag_id
        )
    elif entire_audience:
        recipients = "entire audience"
        print(" ", " ", "Sending to entire audience")

        # send email
        error_msg, campaign_info = mailchimp_utils.create_and_send_campaign(
            audience_id, template_id, subject
        )
    else:  # division is not None
        recipients = f"division {division!r}"
        print(
            " ",
            " ",
            "Sending to division:",
            division,
            f"({len(division_emails)} recipients)",
        )

        email_sent_info["division"] = division

        # get TNS segment id
        error_msg, tns_segment_id = mailchimp_utils.get_or_create_tns_segment(
            audience_id
        )
        if error_msg is not None:
            print(" ", "Error while getting TNS segment:", error_msg)
            return helpers.unsuccessful_notif(
                "Mailchimp error", print_error=False
            )

        # send email
        (
            error_msg,
            campaign_info,
        ) = mailchimp_utils.create_and_send_campaign_to_emails(
            audience_id,
            template_id,
            subject,
            tns_segment_id,
            list(division_emails),
        )

    if error_msg is not None:
        print(" ", "Error while sending email:", error_msg)
        return helpers.unsuccessful_notif(
            "Email send failed", print_error=False
        )
    print(" ", " ", "Created campaign id:", campaign_info["id"])

    email_sent_info["time_sent"] = datetime.utcnow()

    # save Mailchimp template and subject
    success = db.global_state.set_mailchimp_blast_template_id(template_id)
    if not success:
        # it's okay if this fails
        print(" ", "Database error while saving Mailchimp template id")
    success = db.global_state.set_mailchimp_blast_subject(subject)
    if not success:
        # it's okay if this fails
        print(" ", "Database error while saving Mailchimp subject")

    response = {"success": True}

    success = db.sent_emails.add_blast_emails_sent([email_sent_info])
    if not success:
        error_msg = "Database error while saving sent email"
        print(" ", "Error:", error_msg)
        response["error"] = error_msg

    success_msg = f"Successfully sent blast notification to {recipients}"
    response["message"] = success_msg
    return response
