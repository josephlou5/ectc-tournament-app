"""
Helper methods for the roster, which includes the Schools, Users, and
Teams tables.
"""

# =============================================================================

from functools import partial

from db._utils import clear_tables, query
from db.models import School, Team, User, db
from utils import fetch_tms

# =============================================================================


class TeamJoined:
    """A team, with objects referencing each of its team members."""

    @classmethod
    def per_user(cls):
        """Returns a callable that returns a `TeamJoined` object that
        individually fetches every user in each team.

        The fetched users will be cached.
        """

        seen_users = {}

        def get_user(user_id):
            if user_id in seen_users:
                return seen_users[user_id]
            user = query(User, {"id": user_id}).first()
            if user is not None:
                seen_users[user_id] = user
            return user

        return partial(TeamJoined, get_user_func=get_user)

    @classmethod
    def all_users(cls):
        """Returns a callable that returns a `TeamJoined` object.

        All the users in the database will be fetched and cached first.
        """

        users = {user.id: user for user in query(User).all()}

        def get_user(user_id):
            return users.get(user_id, None)

        return partial(TeamJoined, get_user_func=get_user)

    @classmethod
    def join_teams(cls, teams, sort=False):
        joined_teams_iter = map(cls.all_users(), teams)
        if sort:
            return sorted(joined_teams_iter, key=fetch_tms.team_sort_key)
        return joined_teams_iter

    def __init__(self, team, get_user_func):
        self.id = team.id
        self.school = team.school
        self.division = team.division
        self.number = team.number

        self.school_team_code = (team.school.name, team.division, team.number)
        self.name = fetch_tms.school_team_code_to_str(*self.school_team_code)

        valid_emails = set()
        self._all_user_emails = set()
        self._all_user_ids = set()

        def _get_user(user_id):
            if user_id is None:
                return None
            user = get_user_func(user_id)
            if user is None:
                raise ValueError(f"No user with id {user_id}")
            self._all_user_emails.add(user.email)
            self._all_user_ids.add(user.id)
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

    def has_user_id(self, user_id):
        return user_id in self._all_user_ids

    def has_user_email(self, user_email):
        return user_email in self._all_user_emails


# =============================================================================


def get_full_roster(as_json=False):
    schools = query(School).all()
    users = query(User).all()
    teams = query(Team).all()
    full_roster = {"schools": schools, "users": users, "teams": teams}

    if not as_json:
        # convert to TeamJoined objects
        full_roster["teams"] = list(
            TeamJoined.join_teams(full_roster["teams"])
        )
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


def get_all_user_emails():
    """Gets the user emails currently in the database.

    Returns:
        Dict[str, bool]: A mapping from emails to whether the email was
            valid when added to Mailchimp.
    """
    return {user.email: user.email_valid for user in query(User).all()}


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
        raise ValueError(f"School {school_name!r} not found")
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
    for team in TeamJoined.join_teams(division_teams):
        emails.update(team.valid_emails())
    return emails


# =============================================================================


def get_all_teams(school=None, division=None):
    """Returns all the teams.

    If a school name or division is given, the teams will be filtered by
    the given args.

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
    return TeamJoined.join_teams(query(Team, filters).all(), sort=True)


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
    team_joiner = TeamJoined.per_user()
    return None, team_joiner(team)


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

    team_joiner = TeamJoined.all_users()

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
        results[school_team_code] = (None, team_joiner(team_obj))
    return results
