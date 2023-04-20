"""
Fetches information from the TMS spreadsheet.
"""

# =============================================================================

import re
from functools import partial

import google.auth.exceptions
import gspread
import requests.exceptions

import db
from utils import list_of_items

# =============================================================================

ROSTER_WORKSHEET_NAME = "FULL ROSTER"

# Note: If any of these values are changed, they must also be changed in
# `validate_roster()` and the help section on the
# `templates/notifications/index.jinja` page.
ROSTER_REQUIRED_HEADERS = [
    "first name",
    "last name",
    "email",
    "role",
    "school",
]
ROSTER_OPTIONAL_HEADERS = [
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

# These divisions are also in the order they should be sorted in.
DIVISIONS = [
    f"{prefix}{suffix}"
    for prefix in ("P", "Men's ", "Women's ")
    for suffix in "ABC"
]
TEAM_CODE_PATTERN = re.compile(
    rf'(?P<division>{"|".join(f"({division})" for division in DIVISIONS)})'
    r"(?P<number>\d+)"
)

# =============================================================================

# using communications view to get the status and teams of matches
MATCHES_WORKSHEET_NAME = "Communications"

# Note: If any of these values are changed, they must also be changed in
# `fetch_match_teams()`.
MATCHES_HEADERS = [
    "match #",
    "division",
    "round",
    "match status",
    "clean blue team",
    "clean red team",
]

SCHOOL_TEAM_CODE_PATTERN = re.compile(
    rf"(?P<school>[A-Za-z ]+) {TEAM_CODE_PATTERN.pattern}"
)

# same order as the communications view (2023-03-19)
MATCH_NUMBER_HUNDREDS_ORDER = [9, 7, 8, 1, 5, 2, 6, 4, 3]

# The Bootstrap accent colors of each possible status.
MATCH_STATUS_TABLE_ACCENTS = {
    # "In Holding": "warning",
    # "In Staging": "success",
    # "On Route To Ring": "info",
    # "Checked in at Ring": "info",
    # "Competing": "info",
    "Done": "primary",
    "Canceled": "danger",  # in TMS, looks more like secondary
}

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


def id_to_url(spreadsheet_id):
    """Converts a spreadsheet id to a valid spreadsheet url."""
    # this is the method used for the `Spreadsheet.url` property
    return gspread.spreadsheet.SPREADSHEET_DRIVE_URL % spreadsheet_id


# =============================================================================

GLOBAL_SERVICE_ACCOUNT = None


def get_service_account_client(
    service_account_info=None, invalid_prefix=False, force=False
):
    """Gets the service account client.

    If the info is not given, uses the one saved in the database.

    Returns:
        Union[Tuple[str, None], Tuple[None, gspread.Client]]:
            A tuple of an error message, or the service account client.
    """
    global GLOBAL_SERVICE_ACCOUNT, GLOBAL_TMS_SPREADSHEET  # pylint: disable=global-statement

    # fetch info if not given
    from_db = False
    if service_account_info is None:
        invalid_prefix = True
        service_account_info = db.global_state.get_service_account_info()
        if service_account_info is None:
            return "No service account in database", None
        from_db = True

    # check cached service account client
    if not force and GLOBAL_SERVICE_ACCOUNT is not None:
        email = service_account_info.get("client_email", None)
        if (
            email is not None
            and email == GLOBAL_SERVICE_ACCOUNT.auth.service_account_email
        ):
            # assume same service account
            # check that connection is still valid
            try:
                _ = GLOBAL_SERVICE_ACCOUNT.list_spreadsheet_files()
                return None, GLOBAL_SERVICE_ACCOUNT
            except (
                google.auth.exceptions.TransportError,
                requests.exceptions.ConnectionError,
            ) as ex:
                # error is: (
                #   "Connection aborted.",
                #   RemoteDisconnected(
                #     "Remote end closed connection without response"
                #   ),
                # )
                print("!", "Client connection aborted:", ex)
            # refetch the client
            print("!", "Refetching...")
            return get_service_account_client(
                service_account_info=service_account_info,
                invalid_prefix=invalid_prefix,
                force=True,
            )

    # get client
    try:
        client = gspread.service_account_from_dict(
            service_account_info, scopes=gspread.auth.READONLY_SCOPES
        )
    except google.auth.exceptions.MalformedError as ex:
        # if the service account is invalid, reset the spreadsheet
        # object too
        GLOBAL_SERVICE_ACCOUNT = None
        GLOBAL_TMS_SPREADSHEET = None
        if from_db:
            # remove the credentials from the database
            _ = db.global_state.clear_service_account_info()
        error_msg = str(ex)
        if invalid_prefix:
            error_msg = f"Invalid service account credentials: {error_msg}"
        return error_msg, None

    # if the service account was fetched, reset the spreadsheet object
    # (new service account may not have access to cached spreadsheet)
    GLOBAL_SERVICE_ACCOUNT = client
    GLOBAL_TMS_SPREADSHEET = None
    return None, client


# =============================================================================

GLOBAL_TMS_SPREADSHEET = None


def get_tms_spreadsheet(spreadsheet_id=None, force=False):
    """Gets the TMS spreadsheet.

    If the id is not given, uses the one saved in the database.

    Returns:
        Union[Tuple[str, None], Tuple[None, gspread.Spreadsheet]]:
            A tuple of an error message, or the spreadsheet.
    """
    global GLOBAL_TMS_SPREADSHEET  # pylint: disable=global-statement

    # get client
    error_msg, client = get_service_account_client(force=force)
    if error_msg is not None:
        return error_msg, None

    # fetch id if not given
    from_db = False
    if spreadsheet_id is None:
        spreadsheet_id = db.global_state.get_tms_spreadsheet_id()
        if spreadsheet_id is None:
            return "No TMS spreadsheet in database", None
        from_db = True

    # check cached spreadsheet
    if not force and GLOBAL_TMS_SPREADSHEET is not None:
        if GLOBAL_TMS_SPREADSHEET.id == spreadsheet_id:
            # check that connection is still valid
            try:
                _ = GLOBAL_TMS_SPREADSHEET.sheet1
                return None, GLOBAL_TMS_SPREADSHEET
            except (
                google.auth.exceptions.TransportError,
                requests.exceptions.ConnectionError,
            ) as ex:
                # error is: (
                #   "Connection aborted.",
                #   RemoteDisconnected(
                #     "Remote end closed connection without response"
                #   ),
                # )
                print("!", "Spreadsheet connection aborted:", ex)
            # refetch the client and spreadsheet
            print("!", "Refetching...")
            return get_tms_spreadsheet(
                spreadsheet_id=spreadsheet_id, force=True
            )

    # get spreadsheet
    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
    except gspread.SpreadsheetNotFound:
        GLOBAL_TMS_SPREADSHEET = None
        if from_db:
            # remove the id from the database
            _ = db.global_state.clear_tms_spreadsheet_id()
        return "Spreadsheet not found", None
    except gspread.exceptions.APIError as ex:
        GLOBAL_TMS_SPREADSHEET = None
        if from_db:
            # remove the id from the database
            _ = db.global_state.clear_tms_spreadsheet_id()
        error = ex.response.json()["error"]
        if error["code"] == 403 and error["status"] == "PERMISSION_DENIED":
            return (
                (
                    "Service account does not have permission to open the "
                    "spreadsheet"
                ),
                None,
            )
        if error["code"] == 404 and error["status"] == "NOT_FOUND":
            # not sure why this isn't a `SpreadsheetNotFound` error?
            return "Spreadsheet not found", None
        raise

    GLOBAL_TMS_SPREADSHEET = spreadsheet
    return None, spreadsheet


def get_worksheet(spreadsheet, worksheet_name, description=None):
    """Gets the specified worksheet from the given spreadsheet.

    Returns:
        Union[Tuple[str, None], Tuple[None, gspread.Worksheet]]:
            A tuple of an error message, or the worksheet.
    """
    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        if description is None:
            description = "Worksheet"
        return f"{description} {worksheet_name!r} not found", None
    return None, worksheet


# =============================================================================


def school_team_code_to_str(school, division, team_number):
    return f"{school} {division}{team_number}"


def division_sort_key(division):
    try:
        return DIVISIONS.index(division)
    except ValueError:
        # just put everything else at the end
        return len(DIVISIONS)


def school_team_code_sort_key(school_team_code):
    school, division, team_number = school_team_code
    return (school, division_sort_key(division), team_number)


def team_sort_key(team):
    return school_team_code_sort_key(team.school_team_code)


def fetch_roster():
    """Fetches the full team roster from the TMS spreadsheet.

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
                    'row_num': the row number where this user was first
                        seen (for logs)
                'teams': list of:
                    'school': school name
                    'division': team division
                    'number': team number
                    'light': (optional) email
                    'middle': (optional) email
                    'heavy': (optional) email
                    'alternates': list of emails
    """

    def _fetch_error(msg):
        return msg, None, None

    error_msg, spreadsheet = get_tms_spreadsheet()
    if error_msg is not None:
        return _fetch_error(error_msg)

    error_msg, worksheet = get_worksheet(
        spreadsheet, ROSTER_WORKSHEET_NAME, description="Roster spreadsheet"
    )
    if error_msg is not None:
        return _fetch_error(error_msg)

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
    for header in ROSTER_REQUIRED_HEADERS + ROSTER_OPTIONAL_HEADERS:
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
            # allow the first or last name to be empty individually, but
            # at least one must be given
            NAME_HEADERS = ("first name", "last name")
            for header in ROSTER_REQUIRED_HEADERS:
                value = row[header_col_index[header]].strip()
                if value == "" and header not in NAME_HEADERS:
                    row_values["missing_required"].append(f'"{header}"')
                    continue
                row_values[header] = value
            if all(row_values[header] == "" for header in NAME_HEADERS):
                for header in NAME_HEADERS:
                    row_values.pop(header)
                    row_values["missing_required"].append(f'"{header}"')
            for header in ROSTER_OPTIONAL_HEADERS:
                value = row[header_col_index[header]].strip()
                if value == "":
                    value = None
                row_values[header] = value
            yield row_values

    logs, roster = process_roster(yield_row_values)
    invalid_parts = []
    for key in ("users", "teams", "schools"):
        if len(roster[key]) == 0:
            invalid_parts.append(key)
    if len(invalid_parts) > 0:
        invalid_str = list_of_items(invalid_parts, sep="or")
        return _fetch_error(f"Empty roster (no valid {invalid_str} found)")

    # save the last fetched time
    success = db.global_state.set_roster_last_fetched_time()
    if not success:
        return _fetch_error("Database error")

    return None, logs, roster


def process_roster(row_generator):
    """Processes the rows yielded by the given generator.

    Assumes emails uniquely identify each user, but doesn't do any
    rigorous uniqueness checking. That is, emails are taken as they
    appear in the sheet, although there are ways to make a single email
    address different in a strict string comparison. See:
    https://gmail.googleblog.com/2008/03/2-hidden-ways-to-get-more-from-your.html

    Returns:
        Tuple[List, Dict]:
            A list of log messages and the roster in the format:
                'schools': [list of school names]
                'users': list of:
                    'name': name
                    'email': email
                    'role': role
                    'school': school name
                    'row_num': the row number where this user was first
                        seen (for logs)
                'teams': list of:
                    'school': school name
                    'division': team division
                    'number': team number
                    'light': (optional) email
                    'middle': (optional) email
                    'heavy': (optional) email
                    'alternates': list of emails
    """

    logs = []

    def _log(level, msg, row_num):
        logs.append({"level": level, "row_num": row_num, "message": msg})

    # maps: school name -> number of athletes and teams
    schools = {}
    # maps: email -> user
    users = {}
    # maps: email -> whether they are on a poomsae or sparring team
    user_teams = {}
    # maps: (school, division, team number) -> team
    teams = {}

    def _add_school(school):
        if school in schools:
            return False
        schools[school] = {
            "athletes": 0,
            "teams": 0,
        }
        return True

    def _add_user(
        email, first_name, last_name, full_name, role, school, row_num
    ):
        users[email] = {
            "first_name": first_name,
            "last_name": last_name,
            "full_name": full_name,
            "email": email,
            "role": role,
            "school": school,
            "row_num": row_num,
        }
        if role == "ATHLETE":
            schools[school]["athletes"] += 1

    def _add_team(school, division, team_number):
        team = {
            "school": school,
            "division": division,
            "number": team_number,
            "light": None,
            "middle": None,
            "heavy": None,
            "alternates": [],
        }
        teams[school, division, team_number] = team
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
                    break
            else:
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

        first_name = row_data["first name"]
        last_name = row_data["last name"]
        email = row_data["email"].lower()
        role = row_data["role"].upper()
        school = row_data["school"]

        full_name = f"{first_name} {last_name}".strip()
        name_email = f"{full_name} <{email}>"

        if role not in POSSIBLE_ROLES:
            _log_error(f"Invalid role {role!r} (skipped)")
            continue
        is_athlete = role == "ATHLETE"

        if email in users:
            # validate that the user is the same
            seen_before = users[email]
            different = []
            if full_name != seen_before["full_name"]:
                different.append(f"name {full_name!r}")
            if role != seen_before["role"]:
                different.append(f'role "{role}"')
            if school != seen_before["school"]:
                different.append(f"school {school!r}")
            if len(different) > 0:
                _log_error(
                    f'Repeated email "{email}" with different '
                    f"{list_of_items(different)} (skipped)"
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
            if _add_school(school):
                _log_info(f"Added school: {school}")
            _add_user(
                email, first_name, last_name, full_name, role, school, row_num
            )
            _log_info(f"Added {role.lower()}: {name_email} ({school})")
            # shouldn't have any team data
            has_data = []
            for key in ROSTER_OPTIONAL_HEADERS:
                if row_data[key] is not None:
                    has_data.append(key)
            if len(has_data) > 0:
                _log_warning(
                    f"Unnecessary data for {list_of_items(has_data)} "
                    '(not "ATHLETE" role)'
                )
            continue

        # find out which team it is
        team_code = row_data["team code"]
        if team_code is None:
            _log_error("Missing team code (skipped)")
            continue
        team_code_match = TEAM_CODE_PATTERN.fullmatch(team_code)
        if team_code_match is None:
            _log_error(f"Invalid team code {team_code!r} (skipped)")
            continue
        division, team_number = team_code_match.group("division", "number")
        team_number = int(team_number)
        weight_class = row_data["fighting weight class"]
        if weight_class is not None:
            weight_class = weight_class.lower()
        # assume poomsae teams start with "P" and sparring teams do not
        is_sparring_team = not division.startswith("P")
        if is_sparring_team:
            if weight_class is None:
                _log_error(
                    "Missing fighting weight class for sparring team (skipped)"
                )
                continue
            if weight_class not in POSSIBLE_WEIGHT_CLASSES:
                _log_error(f"Invalid weight class {weight_class!r} (skipped)")
                continue
        elif weight_class is not None and weight_class != "alternate":
            # poomsae team with a possible alternate (but other weights
            # emit this warning)
            _log_warning("Unnecessary fighting weight class for poomsae team")
            weight_class = None

        school_team_code = (school, division, team_number)
        team_name = school_team_code_to_str(*school_team_code)
        created_team = False
        if school_team_code in teams:
            team = teams[school_team_code]
            if _is_user_in_team(team, email):
                _log_warning(
                    f"Athlete {name_email} already in team {team_name!r} "
                    "(skipped)"
                )
                continue
            # make sure there's an available spot for sparring team
            if (
                is_sparring_team
                and weight_class != "alternate"
                and team[weight_class] is not None
            ):
                _log_error(
                    f"Team {team_name!r} already has a {weight_class}-weight "
                    "athlete (skipped)"
                )
                continue
        else:
            team = _add_team(*school_team_code)
            created_team = True

        if _add_school(school):
            _log_info(f"Added school: {school}")
        if email not in users:
            _add_user(
                email, first_name, last_name, full_name, role, school, row_num
            )
            _log_info(f"Added athlete: {name_email} ({school})")
        if created_team:
            schools[school]["teams"] += 1
            _log_info(f"Added team: {team_name}")

        # athlete can't be on multiple teams (as non-alternate)
        team_type_key = "sparring" if is_sparring_team else "poomsae"
        if weight_class != "alternate":
            if email not in user_teams:
                user_teams[email] = {
                    "poomsae": False,
                    "sparring": False,
                }
            if user_teams[email][team_type_key]:
                _log_error(
                    f"Athlete {name_email} already on a {team_type_key} team; "
                    f"cannot also be on team {team_name!r}"
                )
                continue

        _add_user_to_team(team, email, weight_class)
        if weight_class is None:
            weight_str = ""
        else:
            weight_str = f" ({weight_class.capitalize()})"
        _log_info(
            f"Added athlete to team: {name_email}{weight_str} on {team_name!r}"
        )

        if weight_class != "alternate":
            user_teams[email][team_type_key] = True

    # at this point, all users must be on at least one team

    for school, stats in schools.items():
        missing = []
        for key, num in stats.items():
            if num == 0:
                missing.append(key)
        if len(missing) > 0:
            missing_str = list_of_items(missing, sep="or")
            _log(
                "WARNING",
                f"School {school!r} does not have any {missing_str}",
                None,
            )

    valid_teams = []
    for school_team_code, team_info in teams.items():
        has_team_members = False
        for key in ("light", "middle", "heavy"):
            if team_info[key] is not None:
                has_team_members = True
                break
        if has_team_members:
            valid_teams.append(team_info)
            continue
        team_name = school_team_code_to_str(*school_team_code)
        _log(
            "ERROR",
            f"Team {team_name!r} has no main team members (skipped)",
            None,
        )

    roster = {
        "schools": list(schools.keys()),
        "users": list(users.values()),
        "teams": valid_teams,
    }
    return logs, roster


# =============================================================================


def match_number_sort_key(match_number):
    try:
        return (
            MATCH_NUMBER_HUNDREDS_ORDER.index(match_number // 100),
            match_number,
        )
    except ValueError:
        # just put everything else at the end
        return (len(MATCH_NUMBER_HUNDREDS_ORDER), match_number)


def _extract_school_team_code(team_name):
    match = SCHOOL_TEAM_CODE_PATTERN.fullmatch(team_name)
    if match is None:
        return {"name": team_name, "valid": False}
    school, division, number = match.group("school", "division", "number")
    return {
        "name": team_name,
        "valid": True,
        "school_team_code": (school, division, int(number)),
    }


def fetch_match_teams(match_numbers):
    """Fetches the team names for the given match numbers.

    Returns:
        Union[Tuple[str, None], Tuple[None, List[Dict]]]:
            A tuple of an error message, or a list of matches in the
            format:
                'number': match number (int)
                'found': True or False
                    If False, the rest of the keys will not be present.
                'division': the division
                'round': the round of XX
                'status': the match status
                'blue_team':
                    'name': the team name
                    'valid': True or False
                        If False, 'team_code' will not be present.
                    'school_team_code':
                        tuple of the school, division, and team number
                'red_team': same as 'blue_team'
    """

    def _fetch_error(msg):
        return msg, None

    remaining = set(match_numbers)
    if len(remaining) == 0:
        # no matches to fetch
        return None, []

    error_msg, spreadsheet = get_tms_spreadsheet()
    if error_msg is not None:
        return _fetch_error(error_msg)

    error_msg, worksheet = get_worksheet(
        spreadsheet, MATCHES_WORKSHEET_NAME, description="Matches spreadsheet"
    )
    if error_msg is not None:
        return _fetch_error(error_msg)

    worksheet_values = worksheet.get_values()
    if len(worksheet_values) == 0:
        return _fetch_error(
            f"Empty matches worksheet {MATCHES_WORKSHEET_NAME!r}"
        )

    worksheet_rows_iter = iter(worksheet_values)

    # look for the header row
    header_indices = None
    possible_header_rows = []
    for i, row in enumerate(worksheet_rows_iter):
        # get the first index of each value in this row
        row_indices = {}
        repeated_indices = set()
        for j, value in enumerate(row):
            value = value.strip().lower()
            if value not in row_indices:
                row_indices[value] = j
            else:
                repeated_indices.add(value)
        filtered_indices = {}
        invalid_row = False
        has_repeated = set()
        for header in MATCHES_HEADERS:
            if header not in row_indices:
                invalid_row = True
                break
            if header in repeated_indices:
                has_repeated.add(header)
            filtered_indices[header] = row_indices[header]
        if invalid_row:
            continue
        if len(has_repeated) > 0:
            possible_header_rows.append(i + 1)
            continue
        header_indices = filtered_indices
        break

    if header_indices is None:
        # could not find the header row
        if len(possible_header_rows) == 0:
            required_headers = ", ".join(
                f'"{header}"' for header in MATCHES_HEADERS
            )
            return _fetch_error(
                "No rows were found with all required headers: "
                f"{required_headers}"
            )
        if len(possible_header_rows) == 1:
            row_str = f"Row {possible_header_rows[0]}"
        else:
            row_str = f"Rows {list_of_items(possible_header_rows)}"
        return _fetch_error(
            f"{row_str} had all required headers, but some were repeated "
            "(ambiguous choices)"
        )

    # look at the remaining rows for the match numbers
    tms_match_statuses = {}
    matches_info = []
    for row in worksheet_rows_iter:
        (
            match_number,
            division,
            round_of,
            match_status,
            blue_team_name,
            red_team_name,
        ) = (row[header_indices[header]].strip() for header in MATCHES_HEADERS)

        if not match_number.isdigit():
            continue
        match_number = int(match_number)

        if match_status != "":
            # don't override previous values, but this should maybe be a
            # warning
            if match_number not in tms_match_statuses:
                tms_match_statuses[match_number] = match_status

        if match_number not in remaining:
            continue

        matches_info.append(
            {
                "number": match_number,
                "found": True,
                "division": division,
                "round": round_of,
                "status": match_status,
                "blue_team": _extract_school_team_code(blue_team_name),
                "red_team": _extract_school_team_code(red_team_name),
            }
        )
        remaining.remove(match_number)

    # save the last seen TMS statuses
    success = db.match_status.set_matches_tms_status(tms_match_statuses)
    if not success:
        return _fetch_error("Database error")

    if len(matches_info) == 0:
        # no matches were found
        return _fetch_error("No matches were found")

    for match_number in remaining:
        matches_info.append(
            {
                "number": match_number,
                "found": False,
            }
        )

    matches_info.sort(key=lambda info: match_number_sort_key(info["number"]))
    return None, matches_info
