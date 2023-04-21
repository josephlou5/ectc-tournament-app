"""
Helper methods for the roster, which includes the Schools, Users, and
Teams tables.
"""

# =============================================================================

from db._utils import clear_tables, query
from db.models import School, Team, User, db
from utils import fetch_tms

# =============================================================================


class TeamJoined:
    """A team, with objects referencing each of its team members."""

    def __init__(self, team):
        self.id = team.id
        self.school = team.school
        self.division = team.division
        self.number = team.number

        self.school_team_code = (team.school.name, team.division, team.number)
        self.name = fetch_tms.school_team_code_to_str(*self.school_team_code)

        valid_emails = set()

        def _get_user(user_id):
            if user_id is None:
                return None
            user = query(User, {"id": user_id}).first()
            if user is None:
                raise ValueError(f"No user with id {user_id}")
            if user.email_valid:
                valid_emails.add(user.email)
            return user

        self.light = _get_user(team.light_id)
        self.middle = _get_user(team.middle_id)
        self.heavy = _get_user(team.heavy_id)
        self.alternates = [
            _get_user(user_id) for user_id in team.get_alternate_ids()
        ]

        self._valid_emails = sorted(valid_emails)

    def valid_emails(self):
        return list(self._valid_emails)


# =============================================================================


def get_full_roster(as_json=False):
    schools = query(School).all()
    users = query(User).all()
    teams = query(Team).all()
    full_roster = {"schools": schools, "users": users, "teams": teams}

    if not as_json:
        # convert to TeamJoined objects
        full_roster["teams"] = list(map(TeamJoined, full_roster["teams"]))
        return full_roster

    def model_as_dict(model):
        return {
            col: getattr(model, col) for col in model.__table__.columns.keys()
        }

    return {
        key: list(map(model_as_dict, values))
        for key, values in full_roster.items()
    }


def clear_roster():
    """Clears the current roster.

    Returns:
        bool: Whether the operation was successful.
    """
    clear_tables(Team, User, School)
    return True


def set_roster(roster):
    """Clears and sets the current roster.

    Assumes the given roster is error-free.

    Args:
        roster (Dict): The roster in the format returned by
            `fetch_tms.fetch_roster()`.

    Returns:
        bool: Whether the operation was successful.
    """

    success = clear_roster()
    if not success:
        return False

    def school_sort_key(school):
        # alphabetical
        return school

    def user_sort_key(user):
        # school, role, email
        role_id = ["COACH", "ATHLETE", "SPECTATOR"].index(user["role"])
        return (user["school"], role_id, user["email"])

    def team_sort_key(team):
        # school, division, team number
        school_team_code = (team["school"], team["division"], team["number"])
        return fetch_tms.school_team_code_sort_key(school_team_code)

    sort_keys = {
        "schools": school_sort_key,
        "users": user_sort_key,
        "teams": team_sort_key,
    }

    def get_from_roster(key):
        return sorted(roster[key], key=sort_keys[key])

    try:
        # create schools in sorted order
        for school_name in get_from_roster("schools"):
            school = School(school_name)
            db.session.add(school)
        # maps: school name -> school id
        school_ids = {}
        for school in query(School).all():
            school_ids[school.name] = school.id

        # create users in school, role, and email order
        for user_info in get_from_roster("users"):
            school_id = school_ids[user_info["school"]]
            user = User(
                user_info["first_name"],
                user_info["last_name"],
                user_info["email"],
                user_info["role"],
                school_id,
                email_valid=user_info.get("email_valid", True),
            )
            db.session.add(user)
        # maps: email -> athlete user id
        athlete_ids = {}
        for user in query(User, {"role": "ATHLETE"}).all():
            athlete_ids[user.email] = user.id

        def get_athlete_id(email):
            if email is None:
                return None
            return athlete_ids[email]

        for team_info in get_from_roster("teams"):
            school_id = school_ids[team_info["school"]]
            team = Team(
                school_id,
                team_info["division"],
                team_info["number"],
                get_athlete_id(team_info["light"]),
                get_athlete_id(team_info["middle"]),
                get_athlete_id(team_info["heavy"]),
                [get_athlete_id(email) for email in team_info["alternates"]],
            )
            db.session.add(team)
    except KeyError:
        # most likely errors are probably:
        # - school not found
        # - team member is not an athlete
        # which will all result in key errors when trying to get the id
        db.session.rollback()
        return False

    db.session.commit()
    return True


# =============================================================================


def get_all_user_emails(email_valid=None):
    """Gets the user emails currently in the database."""
    users = query(User).all()
    if email_valid is None:
        return set(user.email for user in users)
    return set(user.email for user in users if user.email_valid is email_valid)


def is_email_in_roster(email):
    """Returns if the given email is in the roster."""
    user = query(User, {"email": email}).first()
    return user is not None


def get_users_for_school(school_name, roles):
    """Gets the emails of the specified roles for the given school."""
    valid_roles = []
    for role in roles:
        role = role.upper()
        if role not in ("COACH", "SPECTATOR"):
            continue
        valid_roles.append(role)
    if len(valid_roles) == 0:
        return []

    school = query(School, {"name": school_name}).first()
    if school is None:
        raise ValueError(f"School {school_name!r} not found in database")
    school_id = school.id

    role_filter = User.role == valid_roles[0]
    for role in valid_roles[1:]:
        role_filter = role_filter | (User.role == role)
    users = query(User).filter(User.school_id == school_id, role_filter).all()
    return [user.email for user in users]


# =============================================================================


def get_all_divisions():
    """Returns all the divisions in the roster.

    The divisions are returned in the proper sorted order.
    """
    divisions = set()
    for (division,) in query(Team.division).distinct():
        divisions.add(division)
    return sorted(divisions, key=fetch_tms.division_sort_key)


def get_emails_for_division(division):
    """Gets the set of emails of all the users that belong to teams in
    the given division.

    If the resulting set is empty, the division did not have any valid
    emails.
    """
    division_teams = query(Team, {"division": division}).all()
    emails = set()
    for team in map(TeamJoined, division_teams):
        emails.update(team.valid_emails())
    return emails


# =============================================================================


def get_all_teams(school=None, division=None, without_email=None):
    """Returns all the teams.

    If a school name or division is given, the teams will be filtered by
    the given args. If a `without_email` value is given, any teams that
    that user is on will not be returned. Otherwise, all teams will be
    returned.

    The teams are returned in sorted order (by school, division, and
    team number).
    """
    filters = {}
    if school is not None:
        school_obj = query(School, {"name": school}).first()
        if school_obj is None:
            # school doesn't exist
            raise ValueError(f"School {school!r} not found")
        filters["school_id"] = school_obj.id
    if division is not None:
        filters["division"] = division
    if len(filters) == 0:
        filters = None
    all_teams = query(Team, filters).all()
    valid_teams = all_teams
    if without_email is not None:
        # get user
        user = query(User, {"email": without_email}).first()
        if user is None:
            # user doesn't exist, so all teams match
            pass
        elif user.role != "ATHLETE":
            # not an athlete, so all teams match
            pass
        else:
            user_id = user.id
            valid_teams = []
            for team in all_teams:
                # if user not on team, add
                if not (
                    user_id in (team.light_id, team.middle_id, team.heavy_id)
                    or user_id in team.get_alternate_ids()
                ):
                    valid_teams.append(team)

    return sorted(map(TeamJoined, valid_teams), key=fetch_tms.team_sort_key)


def get_team(school, division, team_number):
    """Gets the team object for the given args.

    Returns:
        Union[Tuple[str, None], Tuple[None, TeamJoined]]:
            An error message or the team object.
    """
    if isinstance(school, str):
        # find school id
        school_name = school
        school = query(School, {"name": school_name}).first()
        if school is None:
            return f"School {school_name!r} not found", None
    team = query(
        Team,
        {"school_id": school.id, "division": division, "number": team_number},
    ).first()
    if team is None:
        team_name = fetch_tms.school_team_code_to_str(
            school, division, team_number
        )
        return f"Team {team_name!r} not found", None
    return None, TeamJoined(team)


def get_teams(team_infos):
    """Gets the team objects for the given teams.

    Args:
        team_infos (List[Tuple[str, str, int]]): A list of the school
            team codes, as tuples (school, division, team number).

    Returns:
        Dict[
            Tuple[str, str, int],
            Union[Tuple[str, None], Tuple[None, TeamJoined]]
        ]:
            A mapping from school team codes to either an error message
            or a team object.
    """
    if len(team_infos) == 0:
        return {}
    if len(team_infos) == 1:
        team_info = team_infos[0]
        return {team_info: get_team(*team_info)}

    # get all the teams to reduce the number of database queries
    school_ids = {school.name: school.id for school in query(School).all()}
    teams = {
        (team.school_id, team.division, team.number): team
        for team in query(Team).all()
    }

    results = {}
    for school_team_code in team_infos:
        if school_team_code in results:
            # already processed
            continue
        school_name, division, team_number = school_team_code
        school_id = school_ids.get(school_name, None)
        if school_id is None:
            results[school_team_code] = (
                f"School {school_name!r} not found",
                None,
            )
            continue
        school_id_team_code = (school_id, division, team_number)
        team_obj = teams.get(school_id_team_code, None)
        if team_obj is None:
            team_code_str = fetch_tms.school_team_code_to_str(
                *school_team_code
            )
            results[school_team_code] = (
                f"Team {team_code_str!r} not found",
                None,
            )
            continue
        results[school_team_code] = (None, TeamJoined(team_obj))
    return results


def get_user_teams(email):
    """Returns the team objects that the given email belongs to."""

    # get user
    user = query(User, {"email": email}).first()
    if user is None:
        # user doesn't exist, so no teams
        return []
    if user.role != "ATHLETE":
        # not an athlete, so won't be on any teams
        return []
    user_id = user.id

    # get all teams (because we also need to check alternates)
    all_teams = query(Team).all()

    user_teams = []
    for team in all_teams:
        if (
            user_id in (team.light_id, team.middle_id, team.heavy_id)
            or user_id in team.get_alternate_ids()
        ):
            user_teams.append(TeamJoined(team))
    return sorted(user_teams, key=fetch_tms.team_sort_key)
