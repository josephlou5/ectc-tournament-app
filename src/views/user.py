"""
Views for a (non-admin) user.
"""

# =============================================================================

from flask import request

import db
from utils import fetch_tms
from utils.auth import (
    get_email,
    is_logged_in_admin,
    is_logged_in_in_roster,
    login_required,
)
from utils.server import AppRoutes, _render, get_request_json, unsuccessful

# =============================================================================

app = AppRoutes()

# =============================================================================


@app.route("/subscriptions", methods=["GET", "POST", "DELETE"])
@login_required()
def subscriptions():
    # a user can view this page only if they are an admin (includes
    # super admin) or are in the roster
    if not (is_logged_in_admin() or is_logged_in_in_roster()):
        return _render("user/subscriptions_not_in_roster.jinja")

    user_email = get_email()

    if request.method in ("POST", "DELETE"):
        error_msg, request_args = get_request_json(
            {"key": "all", "type": bool, "required": False},
            {"key": "school", "required": False},
            {"key": "division", "required": False},
        )
        if error_msg is not None:
            return unsuccessful(error_msg)

        if request_args.get("all", False):
            school = request_args.get("school", None)
            division = request_args.get("division", None)

            if school is None and division is None:
                return unsuccessful(
                    'Invalid JSON data: Missing key "school" or "division"'
                )

            for_school = school is not None

            if for_school:
                school = school.strip()
                target = "all school teams"
                specific_target = f"school {school!r}"
                teams_filter = {"school": school}
            else:
                division = division.strip()
                target = "all division teams"
                specific_target = f"division {division!r}"
                teams_filter = {"division": division}

            if request.method == "POST":
                action = f'Subscribing "{user_email}" to'
            else:
                action = f'Unsubscribing "{user_email}" from'
            print(" ", f"{action} all teams for {specific_target}")

            if request.method == "POST":
                # add all teams
                school_team_codes = [
                    team.school_team_code
                    for team in db.roster.get_all_teams(
                        **teams_filter, without_email=user_email
                    )
                ]
                success = db.subscriptions.add_all_teams(
                    user_email, school_team_codes
                )
            else:
                # remove all teams
                if for_school:
                    success = db.subscriptions.remove_school_teams(
                        user_email, school
                    )
                else:
                    success = db.subscriptions.remove_division_teams(
                        user_email, division
                    )
        else:
            target = "team"

            error_msg, team_args = get_request_json(
                "school", "division", {"key": "number", "type": int}
            )
            if error_msg is not None:
                return unsuccessful(error_msg)

            school = team_args["school"].strip()
            team_division = team_args["division"].strip()
            team_number = team_args["number"]

            if request.method == "POST":
                action = f'Subscribing "{user_email}" to'
            else:
                action = f'Unsubscribing "{user_email}" from'
            school_team_code = (school, team_division, team_number)
            team_name = fetch_tms.school_team_code_to_str(*school_team_code)
            print(" ", f"{action} team {team_name!r}")

            if request.method == "POST":
                # add team
                success = db.subscriptions.add_team(
                    user_email, *school_team_code
                )
            else:
                # remove team
                success = db.subscriptions.remove_team(
                    user_email, *school_team_code
                )

        if not success:
            if request.method == "POST":
                action = "Subscribing to"
            else:
                action = "Unsubscribing from"
            return unsuccessful("Database error", f"{action} {target}")

        return {"success": True}

    all_teams = db.roster.get_all_teams()
    if len(all_teams) == 0:
        return _render("user/subscriptions_base.jinja")

    # get subscriptions
    user_subscriptions = db.subscriptions.get_all_subscriptions(user_email)

    # get all user team codes
    user_school_team_codes = set(
        team.school_team_code for team in db.roster.get_user_teams(user_email)
    )

    divisions = set()

    # maps: school -> division -> team number ->
    #   {"name": team name, "is_subscribed", "is_user_on_team"}
    team_subscriptions = {}
    for team in all_teams:
        school_team_code = team.school_team_code
        school, division, team_number = school_team_code

        if school not in team_subscriptions:
            team_subscriptions[school] = {}
        school_subscriptions = team_subscriptions[school]

        divisions.add(division)
        if division not in school_subscriptions:
            school_subscriptions[division] = {}
        division_subscriptions = school_subscriptions[division]

        division_subscriptions[team_number] = {
            "name": team.name,
            "is_subscribed": school_team_code in user_subscriptions,
            "is_user_on_team": school_team_code in user_school_team_codes,
        }

    return _render(
        "user/subscriptions.jinja",
        subscriptions=team_subscriptions,
        divisions=sorted(divisions, key=fetch_tms.division_sort_key),
    )
