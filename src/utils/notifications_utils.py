"""
Utilities for the notifications view.
"""

# =============================================================================

from pathlib import Path

from utils import fetch_tms

# =============================================================================

STATIC_FOLDER = (Path(__file__).parent / ".." / "static").resolve()
FETCH_ROSTER_LOGS_FILE = STATIC_FOLDER / "fetch_roster_logs.json"

# Instead of injecting these characters into the Jinja template as a
# JavaScript RegExp object, the client-side JavaScript should be
# manually updated in `src/templates/notifications/index.jinja` whenever
# this value changes.
EMAIL_SUBJECT_VALID_CHARS = "-_+.,!#&()[]|:;'\"/?"
EMAIL_SUBJECT_VALID_CHARS_SET = set(EMAIL_SUBJECT_VALID_CHARS)

# THe maximum number of matches that can be fetched at a time.
MAX_NUM_MATCHES = 50

VALID_SUBJECT_PLACEHOLDERS = {
    "match",
    "division",
    "round",
    "blueteam",
    "redteam",
    "team",
}

# =============================================================================


def unsuccessful_notif(
    general=None, template=None, subject=None, print_error=True
):
    errors = {}
    if general is not None:
        errors["GENERAL"] = general
    if template is not None:
        errors["TEMPLATE"] = template
    if subject is not None:
        errors["SUBJECT"] = subject
    if len(errors) == 0:
        raise ValueError("No errors given")
    if print_error:
        for location, error_msg in errors.items():
            if location == "GENERAL":
                print(" ", "Error:", error_msg)
            else:
                print(" ", f"{location.capitalize()} error:", error_msg)
    return {"success": False, "errors": errors}


# =============================================================================


def has_fetch_roster_logs():
    return FETCH_ROSTER_LOGS_FILE.exists()


# =============================================================================


def parse_matches_query(matches_query):
    """Handwritten parser to parse a match list str, with spaces or
    commas separating match groups, and with dashes representing match
    ranges.

    The parser is pretty forgiving; it allows numbers starting with 0s
    and has no restrictions on the value ranges. However, the end of
    ranges must be at least as large as the start of the range. Also,
    there is a cutoff on the number of matches that can be specified.
    """

    def _parse_error(msg, index=None):
        if index is not None:
            msg = f"Position {index+1}: {msg}"
        return msg, None

    # insertion-order collection of match numbers
    match_numbers = {}
    # a buffer of the last seen match number
    last_num = None
    # index of the seen dash
    saw_dash = None
    # the digits of the current number
    current_number = []

    def _add_number(i, c=None):
        nonlocal last_num, saw_dash

        if len(current_number) == 0:
            return None

        num_start_i = i - len(current_number)
        num = int("".join(current_number))
        current_number.clear()

        if saw_dash is not None:
            # end a range
            if num < last_num:
                return (
                    f"Position {num_start_i}: "
                    "Range end is smaller than range start"
                )
            if num == last_num:
                match_numbers[last_num] = True
            else:
                for x in range(last_num, num + 1):
                    match_numbers[x] = True
            last_num = None
            saw_dash = None
        else:
            # single match number
            if last_num is not None:
                match_numbers[last_num] = True
            last_num = num

        if len(match_numbers) > MAX_NUM_MATCHES:
            return f"Too many matches specified (max {MAX_NUM_MATCHES})"

        return None

    for i, c in enumerate(matches_query):
        if c.isspace() or c in (",", "-"):
            # end of a number
            error_msg = _add_number(i, c)
            if error_msg is not None:
                return _parse_error(error_msg)
            if c == ",":
                # explicitly start a new group (dashes cannot go across
                # commas)
                if saw_dash is not None:
                    return _parse_error(
                        f"Position {saw_dash+1}: Dash without end number"
                    )
                if last_num is not None:
                    match_numbers[last_num] = True
                last_num = None
            elif c == "-":
                if last_num is None:
                    return _parse_error(
                        f"Position {i+1}: Dash without a start number"
                    )
                if saw_dash is not None:
                    return _parse_error(f"Position {i+1}: invalid dash")
                saw_dash = i
            continue
        if c.isdigit():
            current_number.append(c)
            continue
        return _parse_error(f"Position {i+1}: unknown character: {c}")
    error_msg = _add_number(len(matches_query))
    if error_msg is not None:
        return _parse_error(error_msg)

    if saw_dash is not None:
        return _parse_error(f"Position {saw_dash+1}: Dash without end number")

    if last_num is not None:
        match_numbers[last_num] = True
    if len(match_numbers) > MAX_NUM_MATCHES:
        return _parse_error(
            f"Too many matches specified (max {MAX_NUM_MATCHES})"
        )

    return None, list(match_numbers.keys())


def clean_matches_query(match_numbers):
    """Returns a "clean" version of a matches query string that
    represents the specified match numbers.
    """
    groups = []
    group_start = None
    group_end = None

    def add_group():
        if group_start == group_end:
            groups.append(str(group_start))
        else:
            groups.append(f"{group_start}-{group_end}")

    # find all consecutive groups
    for num in sorted(set(match_numbers), key=fetch_tms.match_number_sort_key):
        if group_start is not None:
            # has to be in the same hundred
            if (num // 100 == group_end // 100) and num == group_end + 1:
                group_end = num
                continue
            add_group()
        group_start = num
        group_end = num
    if group_start is not None:
        add_group()
    return ",".join(groups)


# =============================================================================


def validate_subject(subject, blast=False):
    """Validates a given subject with optional placeholder values.

    If `blast` is True, placeholders are not allowed. Otherwise,
    converts all placeholder names to lowercase.

    Returns:
        Union[Tuple[str, None], Tuple[None, str]]:
            An error message, or the validated subject.
    """

    def _error(msg):
        return msg, None

    subject_chars = []

    in_placeholder = False
    placeholder_chars = []
    has_match_number = False
    for i, c in enumerate(subject):
        if c == "{":
            if blast:
                return _error(
                    f"Index {i+1}: invalid open bracket: no placeholders in "
                    "blast email subject"
                )
            if in_placeholder:
                return _error(
                    f"Index {i+1}: invalid open bracket: cannot have a nested "
                    "placeholder"
                )
            in_placeholder = True
        elif c == "}":
            if blast:
                return _error(f"Index {i+1}: invalid character: {c}")
            if not in_placeholder:
                return _error(
                    f"Index {i+1}: invalid close bracket: not in a placeholder"
                )
            placeholder_str = "".join(placeholder_chars)
            bracket_index = i - len(placeholder_str)
            if placeholder_str == "":
                return _error(f"Index {bracket_index}: empty placeholder")
            if placeholder_str == "match":
                has_match_number = True
            elif placeholder_str not in VALID_SUBJECT_PLACEHOLDERS:
                return _error(
                    f"Index {bracket_index}: unknown placeholder "
                    f'"{placeholder_str}"'
                )
            # reset placeholder values
            in_placeholder = False
            placeholder_chars.clear()
        elif in_placeholder:
            if not c.isalpha():
                return _error(
                    f"Index {i+1}: invalid character inside placeholder: {c}"
                )
            placeholder_chars.append(c.lower())
        elif not (
            c.isalpha()
            or c.isdigit()
            or c == " "
            or c in EMAIL_SUBJECT_VALID_CHARS_SET
        ):
            return _error(f"Index {i+1}: invalid character: {c}")

        if in_placeholder:
            subject_chars.append(c.lower())
        else:
            subject_chars.append(c)
    if in_placeholder:
        bracket_index = len(subject) - len(placeholder_chars)
        return _error(f"Index {bracket_index}: unclosed placeholder")
    if not blast and not has_match_number:
        return _error('Missing "{match}" placeholder')
    # valid!
    return None, "".join(subject_chars)


def format_team_subjects(subject, match_info):
    """Formats a subject for each team with the possible placeholder
    values.

    Returns:
        Dict[str, str]: The subject for each team color in the format:
            'blue_team': subject
            'red_team': subject
        Note that the two subjects may be the same.
    """

    def _team_name(team_info):
        return fetch_tms.school_team_code_to_str(
            *team_info["school_team_code"]
        )

    blue_team = _team_name(match_info["blue_team"])
    red_team = _team_name(match_info["red_team"])
    kwargs = {
        "match": match_info["number"],
        "division": match_info["division"],
        "round": match_info["round"],
        "blueteam": blue_team,
        "redteam": red_team,
    }
    return {
        "blue_team": subject.format(**kwargs, team=blue_team),
        "red_team": subject.format(**kwargs, team=red_team),
    }
