"""
Views for a (non-admin) user.
"""

# =============================================================================

from flask import request

import db
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
            "school",
            {"key": "all", "type": bool, "required": False},
            {"key": "code", "type": str, "required": False},
        )
        if error_msg is not None:
            return unsuccessful(error_msg)

        school = request_args["school"].strip()

        if request_args.get("all", False):
            target = "all school teams"

            if request.method == "POST":
                action = f'Subscribing "{user_email}" to'
            else:
                action = f'Unsubscribing "{user_email}" from'
            print(" ", f"{action} all teams for school {school!r}")

            if request.method == "POST":
                # add all teams
                school_team_codes = db.roster.get_all_team_names(school=school)
                success = db.subscriptions.add_school_teams(
                    user_email, school, school_team_codes
                )
            else:
                # remove all teams
                success = db.subscriptions.remove_school_teams(
                    user_email, school
                )
        else:
            target = "team"

            team_code = request_args.get("code", None)
            if team_code is None:
                return unsuccessful('Invalid JSON data: Missing "code"')

            if request.method == "POST":
                action = f'Subscribing "{user_email}" to'
            else:
                action = f'Unsubscribing "{user_email}" from'
            school_team_code = " ".join((school, team_code))
            print(" ", f"{action} team {school_team_code!r}")

            if request.method == "POST":
                # add team
                success = db.subscriptions.add_team(
                    user_email, school, team_code
                )
            else:
                # remove team
                success = db.subscriptions.remove_team(
                    user_email, school, team_code
                )

        if not success:
            if request.method == "POST":
                action = "Subscribing to"
            else:
                action = "Unsubscribing from"
            return unsuccessful("Database error", f"{action} {target}")

        return {"success": True}

    # get subscriptions
    user_subscriptions = db.subscriptions.get_all_teams(user_email)

    team_subscriptions = {}
    for school, team_code in db.roster.get_all_team_names():
        if school not in team_subscriptions:
            team_subscriptions[school] = {}
        is_subscribed = (school, team_code) in user_subscriptions
        team_subscriptions[school][team_code] = is_subscribed

    # get all user team codes
    user_team_codes = set(
        (team.school.name, team.code)
        for team in db.roster.get_user_teams(user_email)
    )

    return _render(
        "user/subscriptions.jinja",
        subscriptions=team_subscriptions,
        user_team_codes=user_team_codes,
    )
