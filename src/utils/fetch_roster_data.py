"""
Fetches the full team roster from the given spreadsheet link.
"""

# =============================================================================

import re
from functools import partial

import google.auth.exceptions
import gspread

import db

# =============================================================================

ROSTER_WORKSHEET_NAME = "FULL ROSTER"

# Note: If any of these values are changed, they must also be changed in
# `validate_roster()`.
REQUIRED_COLUMNS = [
    "name",
    "email",
    "role",
    "school",
]
OPTIONAL_COLUMNS = [
    "team code",
    "fighting weight class",
]

POSSIBLE_ROLES = [
    "COACH",
    "ATHLETE",
    "SPECTATOR",
]
POSSIBLE_WEIGHT_CLASSES = [
    "light",
    "middle",
    "heavy",
    "alternate",
]

TEAM_CODE_PATTERN = re.compile(r"(P|((Men|Women)'s ))[ABC]\d+")

# =============================================================================


def url_to_id(url):
    """Converts a spreadsheet url to the spreadsheet id.

    Returns:
        Optional[str]: The spreadsheet id, or None if it could not be
            found.
    """
    try:
        return gspread.utils.extract_id_from_url(url)
    except gspread.exceptions.NoValidUrlKeyFound:
        return None


def id_to_url(spreadsheet_id, worksheet_id=None):
    """Converts a spreadsheet id to a corresponding link."""
    # a valid spreadsheet link as of 2023-03-06
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
    if worksheet_id is not None:
        url += f"/edit#gid={worksheet_id}"
    return url


# =============================================================================

GLOBAL_SERVICE_ACCOUNT = None


def get_service_account_client(service_account_info):
    """Gets the service account using the given info.

    Returns:
        Union[Tuple[str, None], Tuple[None, gspread.Client]]:
            A tuple of an error message, or the service account client.
    """
    global GLOBAL_SERVICE_ACCOUNT  # pylint: disable=global-statement
    # check cached service account client
    if GLOBAL_SERVICE_ACCOUNT is not None:
        email = service_account_info["client_email"]
        if email == GLOBAL_SERVICE_ACCOUNT.auth.service_account_email:
            # assume same service account
            return None, GLOBAL_SERVICE_ACCOUNT
    try:
        client = gspread.service_account_from_dict(
            service_account_info, scopes=gspread.auth.READONLY_SCOPES
        )
    except google.auth.exceptions.MalformedError as ex:
        GLOBAL_SERVICE_ACCOUNT = None
        return str(ex), None
    GLOBAL_SERVICE_ACCOUNT = client
    return None, client


def fetch(url):
    """Fetches the full team roster from the given spreadsheet link.

    No validation is done beyond required and optional columns.

    Returns:
        Union[Tuple[str, None, None], Tuple[None, List, Dict]]:
            A tuple of: an error message, a list of log messages, and
            the full roster in the format:
                'schools': [list of school names]
                'users': list of:
                    'name': name
                    'email': email
                    'role': role
                    'school': school name
                'teams': list of:
                    'school': school name
                    'code': team code
                    'light': (optional) email
                    'middle': (optional) email
                    'heavy': (optional) email
                    'alternates': list of emails
    """

    def _fetch_error(msg):
        return msg, None, None

    service_account_info = db.global_state.get_service_account_info()
    if service_account_info is None:
        return _fetch_error("No service account in database")

    error_msg, client = get_service_account_client(service_account_info)
    if error_msg is not None:
        return _fetch_error(
            f"Invalid service account credentials: {error_msg}"
        )

    spreadsheet_id = url_to_id(url)
    if spreadsheet_id is None:
        return _fetch_error("Invalid spreadsheet link")

    # get spreadsheet and worksheet
    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
    except gspread.SpreadsheetNotFound:
        return _fetch_error("Spreadsheet not found")
    except gspread.exceptions.APIError as ex:
        error = ex.response.json()["error"]
        if error["code"] == 403 and error["status"] == "PERMISSION_DENIED":
            return _fetch_error(
                "Service account does not have permission to open the "
                "spreadsheet"
            )
        if error["code"] == 404 and error["status"] == "NOT_FOUND":
            # not sure why this isn't a `SpreadsheetNotFound` error?
            return _fetch_error("Spreadsheet not found")
        raise
    try:
        worksheet = spreadsheet.worksheet(ROSTER_WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        return _fetch_error(
            f"Roster worksheet {ROSTER_WORKSHEET_NAME!r} not found"
        )

    worksheet_values = worksheet.get_values()
    if len(worksheet_values) == 0:
        return _fetch_error(
            f"Empty roster worksheet {ROSTER_WORKSHEET_NAME!r}"
        )

    header_row, *rows = worksheet_values

    if len(rows) == 0:
        return _fetch_error(
            f"Empty roster worksheet {ROSTER_WORKSHEET_NAME!r}"
        )

    # first row should (uniquely) contain all the headers
    # maps: header -> column index
    header_col_index = {}
    repeated = set()
    for i, header in enumerate(header_row):
        header_normalized = header.strip().lower()
        if header_normalized in header_col_index:
            repeated.add(header_normalized)
        else:
            header_col_index[header_normalized] = i
    non_unique = []
    missing = []
    for header in REQUIRED_COLUMNS + OPTIONAL_COLUMNS:
        if header in repeated:
            non_unique.append(f'"{header}"')
        elif header not in header_col_index:
            missing.append(f'"{header}"')
    if len(non_unique) > 0:
        non_unique_str = ", ".join(non_unique)
        return _fetch_error(
            f"Invalid roster worksheet {ROSTER_WORKSHEET_NAME!r}: "
            f"repeated headers {non_unique_str}"
        )
    if len(missing) > 0:
        missing_str = ", ".join(missing)
        return _fetch_error(
            f"Invalid roster worksheet {ROSTER_WORKSHEET_NAME!r}: "
            f"missing headers {missing_str}"
        )

    def yield_row_values():
        for i, row in enumerate(rows):
            row_values = {"row_num": i + 2, "missing_required": []}
            for header in REQUIRED_COLUMNS:
                value = row[header_col_index[header]].strip()
                if value == "":
                    row_values["missing_required"].append(f'"{header}"')
                else:
                    row_values[header] = value
            for header in OPTIONAL_COLUMNS:
                value = row[header_col_index[header]].strip()
                if value == "":
                    value = None
                row_values[header] = value
            yield row_values

    logs, roster = process_roster(yield_row_values)
    for key in ("users", "teams", "schools"):
        if len(roster[key]) == 0:
            return _fetch_error(f"Empty roster (no {key} found)")

    spreadsheet_url_with_worksheet = id_to_url(spreadsheet_id, worksheet.id)
    success = db.global_state.set_last_fetched_spreadsheet_url(
        spreadsheet_url_with_worksheet
    )
    if not success:
        return _fetch_error("Unknown database error; please try again later")

    return None, logs, roster


# =============================================================================


def _list_of_items(items):
    if len(items) == 0:
        return None
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return " and ".join(items)
    return ", ".join(items[:-1]) + ", and " + items[-1]


def process_roster(row_generator):
    """Processes the rows yielded by the given generator.

    Assumes emails uniquely identify each user, but doesn't do any
    rigorous email checking. That is, emails are taken as they were
    entered in the sheet, although they are technically case insensitive
    and dot insensitive and parts after a "+" character can be ignored.

    Returns:
        Tuple[List, Dict]:
            A list of log messages and the roster in the format:
                'schools': [list of school names]
                'users': list of:
                    'name': name
                    'email': email
                    'role': role
                    'school': school name
                'teams': list of:
                    'school': school name
                    'code': team code
                    'light': (optional) email
                    'middle': (optional) email
                    'heavy': (optional) email
                    'alternates': list of emails
    """

    logs = []

    def _log(level, msg, row_num):
        logs.append({"level": level, "row_num": row_num, "message": msg})

    # maps: school name -> true
    schools = {}
    # maps: email -> user
    users = {}
    # maps: (school, code) -> team
    teams = {}

    def _add_user(email, name, role, school):
        users[email] = {
            "name": name,
            "email": email,
            "role": role,
            "school": school,
        }

    def _add_team(school, team_code):
        team = {
            "school": school,
            "code": team_code,
            "light": None,
            "middle": None,
            "heavy": None,
            "alternates": [],
        }
        teams[school, team_code] = team
        return team

    def _is_user_in_team(team, email):
        for key in ("light", "middle", "heavy"):
            if team[key] == email:
                return True
        if email in team["alternates"]:
            return True
        return False

    def _add_user_to_team(team, email, weight_class=None):
        if weight_class is None:
            # poomsae team: just add wherever fits
            for key in ("light", "middle", "heavy"):
                if team[key] is None:
                    team[key] = email
                    return
            team["alternates"].append(email)
        else:
            # sparring team: add for proper weight class
            # assume the weight class is not taken yet
            if weight_class == "alternate":
                team["alternates"].append(email)
            else:
                team[weight_class] = email

    for row_data in row_generator():
        row_num = row_data["row_num"]
        _log_info = partial(_log, "INFO", row_num=row_num)
        _log_error = partial(_log, "ERROR", row_num=row_num)
        _log_warning = partial(_log, "WARNING", row_num=row_num)

        missing_required = row_data["missing_required"]
        if len(missing_required) > 0:
            missing_str = ", ".join(missing_required)
            _log_error(f"Missing required values: {missing_str}")
            continue

        name = row_data["name"]
        email = row_data["email"]
        role = row_data["role"].upper()
        school = row_data["school"]

        name_email = f"{name} <{email}>"

        if role not in POSSIBLE_ROLES:
            _log_error(f'Invalid role "{role}" (skipped)')
            continue
        is_athlete = role == "ATHLETE"

        if email in users:
            # validate that the user is the same
            seen_before = users[email]
            different = []
            if name != seen_before["name"]:
                different.append(f"name {name!r}")
            if role != seen_before["role"]:
                different.append(f'role "{role}"')
            if school != seen_before["school"]:
                different.append(f"school {school!r}")
            if len(different) > 0:
                _log_error(
                    f'Repeated email "{email}" with different '
                    f"{_list_of_items(different)} (skipped)"
                )
                continue

            # can skip non-athletes
            if not is_athlete:
                # note: not checking the team data columns
                _log_warning(
                    f'No need to repeat a "{role}" user row (skipped)'
                )
                continue

        # simple case: non-athletes
        if not is_athlete:
            if school not in schools:
                schools[school] = True
                _log_info(f"Added school: {school}")
            _add_user(email, name, role, school)
            _log_info(f"Added {role.lower()}: {name_email} ({school})")
            # shouldn't have any team data
            has_data = []
            for key in OPTIONAL_COLUMNS:
                if row_data[key] is not None:
                    has_data.append(key)
            if len(has_data) > 0:
                _log_warning(
                    f"Unnecessary data for {_list_of_items(has_data)} "
                    '(not "ATHLETE" role)'
                )
            continue

        # find out which team it is
        team_code = row_data["team code"]
        if team_code is None:
            _log_error("Missing team code (skipped)")
            continue
        if TEAM_CODE_PATTERN.fullmatch(team_code) is None:
            _log_error(f"Invalid team code {team_code!r} (skipped)")
            continue
        weight_class = row_data["fighting weight class"]
        if weight_class is not None:
            weight_class = weight_class.lower()
        # assume poomsae teams start with "P" and sparring teams do not
        is_sparring_team = team_code[0].upper() != "P"
        if is_sparring_team:
            if weight_class is None:
                _log_error(
                    "Missing fighting weight class for sparring team (skipped)"
                )
                continue
            if weight_class not in POSSIBLE_WEIGHT_CLASSES:
                _log_error(f"Invalid weight class {weight_class!r} (skipped)")
                continue
        elif not is_sparring_team and weight_class is not None:
            _log_warning("Unnecessary fighting weight class for poomsae team")
            weight_class = None

        school_team = (school, team_code)
        school_team_str = " ".join(school_team)
        created_team = False
        if school_team in teams:
            team = teams[school_team]
            if _is_user_in_team(team, email):
                _log_warning(
                    f"Athlete already in team {school_team_str!r} (skipped)"
                )
                continue
            # make sure there's an available spot for sparring team
            if (
                is_sparring_team
                and weight_class != "alternate"
                and team[weight_class] is not None
            ):
                _log_error(
                    f"Team {school_team_str!r} already has a "
                    f"{weight_class}-weight athlete (skipped)"
                )
                continue
        else:
            team = _add_team(school, team_code)
            created_team = True

        if school not in schools:
            schools[school] = True
            _log_info(f"Added school: {school}")
        if email not in users:
            _add_user(email, name, role, school)
            _log_info(f"Added athlete: {name_email} ({school})")
        if created_team:
            _log_info(f"Added team: {school_team_str}")

        _add_user_to_team(team, email, weight_class)
        msg = f"Added athlete {name_email} to team: {school_team_str}"
        if is_sparring_team:
            msg += f" ({weight_class.capitalize()})"
        _log_info(msg)

    roster = {
        "schools": list(schools.keys()),
        "users": list(users.values()),
        "teams": list(teams.values()),
    }
    return logs, roster
