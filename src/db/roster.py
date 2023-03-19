"""
Helper methods for the roster, which includes the Schools, Users, and
Teams tables.
"""

# =============================================================================

from db._utils import query
from db.models import EmailSent, School, Team, TMSMatchStatus, User, db

# =============================================================================


class TeamJoined:
    """A team, with objects referencing each of its team members."""

    def __init__(self, team):
        self.id = team.id
        self.school = team.school
        self.code = team.code
        self.school_code = f"{self.school.name} {self.code}"

        def _get_user(user_id):
            if user_id is None:
                return None
            user = query(User, {"id": user_id}).first()
            if user is None:
                raise ValueError(f"No user with id {user_id}")
            return user

        self.light = _get_user(team.light_id)
        self.middle = _get_user(team.middle_id)
        self.heavy = _get_user(team.heavy_id)
        self.alternates = [
            _get_user(user_id) for user_id in team.get_alternate_ids()
        ]


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
    # delete all the tables and add them again (resets id counters)
    # https://stackoverflow.com/a/49644099
    # in this particular order due to foreign key constraints
    tables = [
        table.__table__
        for table in (Team, User, School, TMSMatchStatus, EmailSent)
    ]
    db.metadata.drop_all(bind=db.engine, tables=tables, checkfirst=True)
    db.metadata.create_all(bind=db.engine, tables=tables)
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
        # school, team code
        # since team codes contain numbers, sort by length first
        code = team["code"]
        return (team["school"], len(code), code)

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
                user_info["name"],
                user_info["email"],
                user_info["role"],
                school_id,
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
                team_info["code"],
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


def get_team(school, team_code):
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
    team = query(Team, {"school_id": school.id, "code": team_code}).first()
    if team is None:
        return f'Team "{school.name} {team_code}" not found', None
    return None, TeamJoined(team)


def get_teams(team_infos):
    """Gets the team objects for the given teams.

    Args:
        team_infos (List[Tuple[str, str]]): A list of the school names
            and team codes.

    Returns:
        Dict[
            Tuple[str, str],
            Union[Tuple[str, None], Tuple[None, TeamJoined]]
        ]:
            A mapping from school names and team codes to either an
            error message or a team object.
    """
    if len(team_infos) == 0:
        return {}
    if len(team_infos) == 1:
        team_info = team_infos[0]
        return {team_info: get_team(*team_info)}

    # get all the teams to reduce the number of database queries
    schools = {school.name: school.id for school in query(School).all()}
    teams = {(team.school_id, team.code): team for team in query(Team).all()}

    results = {}
    for school_team_code in team_infos:
        if school_team_code in results:
            continue
        school_name, team_code = school_team_code
        if school_name not in schools:
            results[school_team_code] = (
                f"School {school_name!r} not found",
                None,
            )
            continue
        school_id = schools[school_name]
        school_id_team_code = (school_id, team_code)
        if school_id_team_code not in teams:
            results[school_team_code] = (
                f'Team "{school_name} {team_code}" not found',
                None,
            )
            continue
        results[school_team_code] = (
            None,
            TeamJoined(teams[school_id_team_code]),
        )
    return results
