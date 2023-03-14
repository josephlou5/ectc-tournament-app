"""
Helper methods for the roster, which includes the Schools, Users, and
Teams tables.
"""

# =============================================================================

from db._utils import query
from db.models import School, Team, User, db

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


def set_roster(roster):
    """Clears and sets the current roster.

    Assumes the given roster is error-free.

    Args:
        roster (Dict): The roster in the format returned by
            `fetch_tms.fetch_roster()`.

    Returns:
        bool: Whether the operation was successful.
    """

    # delete all the tables and add them again (resets id counters)
    # https://stackoverflow.com/a/49644099
    # in this particular order due to foreign key constraints
    tables = [table.__table__ for table in (Team, User, School)]
    db.metadata.drop_all(bind=db.engine, tables=tables, checkfirst=True)
    db.metadata.create_all(bind=db.engine, tables=tables)

    try:
        for school_name in roster["schools"]:
            school = School(school_name)
            db.session.add(school)
        # maps: school name -> school id
        school_ids = {}
        for school in query(School).all():
            school_ids[school.name] = school.id

        for user_info in roster["users"]:
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

        for team_info in roster["teams"]:
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
