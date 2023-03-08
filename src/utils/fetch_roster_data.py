"""
Fetches the full team roster from the given spreadsheet link.
"""

# =============================================================================

import google.auth.exceptions
import gspread

import db

# =============================================================================

ROSTER_WORKSHEET_NAME = "FULL ROSTER"
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
        Union[Tuple[str, None], Tuple[None, List[Dict]]]:
            A tuple of an error message, or a list of each row in the
            sheet, represented as a dict with the lowercase keys of all
            the required and optional columns.
    """

    service_account_info = db.global_state.get_service_account_info()
    if service_account_info is None:
        return "No service account in database", None

    error_msg, client = get_service_account_client(service_account_info)
    if error_msg is not None:
        return f"Invalid service account credentials: {error_msg}", None

    spreadsheet_id = url_to_id(url)
    if spreadsheet_id is None:
        return "Invalid spreadsheet link", None

    try:
        spreadsheet = client.open_by_key(spreadsheet_id)
    except gspread.SpreadsheetNotFound:
        return "Spreadsheet not found", None
    except gspread.exceptions.APIError as ex:
        error = ex.response.json()["error"]
        if error["code"] == 403 and error["status"] == "PERMISSION_DENIED":
            return (
                "Service account does not have permission to open the "
                "spreadsheet",
                None,
            )
        if error["code"] == 404 and error["status"] == "NOT_FOUND":
            # not sure why this isn't a `SpreadsheetNotFound` error?
            return "Spreadsheet not found", None
        raise
    try:
        worksheet = spreadsheet.worksheet(ROSTER_WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        return f"Roster worksheet {ROSTER_WORKSHEET_NAME!r} not found", None

    worksheet_values = worksheet.get_values()
    if len(worksheet_values) == 0:
        return f"Empty roster worksheet {ROSTER_WORKSHEET_NAME!r}", None

    header_row, *rows = worksheet_values

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
        return (
            (
                f"Invalid roster worksheet {ROSTER_WORKSHEET_NAME!r}: "
                f"repeated headers {non_unique_str}"
            ),
            None,
        )
    if len(missing) > 0:
        missing_str = ", ".join(missing)
        return (
            (
                f"Invalid roster worksheet {ROSTER_WORKSHEET_NAME!r}: "
                f"missing headers {missing_str}"
            ),
            None,
        )

    roster = []
    for row in rows:
        athlete_data = {}
        missing_required = False
        for header in REQUIRED_COLUMNS:
            value = row[header_col_index[header]].strip()
            if value == "":
                missing_required = True
                break
            athlete_data[header] = value
        if missing_required:
            # skip: assume invalid
            continue
        for header in OPTIONAL_COLUMNS:
            value = row[header_col_index[header]].strip()
            if value == "":
                value = None
            athlete_data[header] = value
        roster.append(athlete_data)

    if len(roster) == 0:
        return "Empty roster (no valid rows found)", None

    spreadsheet_url_with_worksheet = id_to_url(spreadsheet_id, worksheet.id)
    success = db.global_state.set_last_fetched_spreadsheet_url(
        spreadsheet_url_with_worksheet
    )
    if not success:
        return "Unknown database error; please try again later", None

    return None, roster
