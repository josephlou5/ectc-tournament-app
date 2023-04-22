"""
General utilities.
"""

# =============================================================================

import json
from pathlib import Path

import pytz

# =============================================================================

UTC_TZ = pytz.utc
EASTERN_TZ = pytz.timezone("US/Eastern")

DATETIME_FMT = "%Y-%m-%d %H:%M:%S"

STATIC_FOLDER = (Path(__file__).parent / ".." / "static").resolve()

# =============================================================================


def json_dump_compact(data, **kwargs):
    """Dumps the given data in the most compact JSON format."""
    kwargs.pop("separators", None)
    return json.dumps(data, separators=(",", ":"), **kwargs)


# =============================================================================


def dt_to_timezone(dt, tz=EASTERN_TZ):
    """Converts a UTC datetime object into the given timezone."""
    if dt is None:
        return None
    if isinstance(tz, str):
        tz = pytz.timezone(tz)
    if dt.tzinfo is None:
        dt = UTC_TZ.localize(dt)
    return dt.astimezone(tz)


def dt_str(dt, fmt=DATETIME_FMT):
    """Returns a string representation of the given datetime."""
    if dt is None:
        return None
    return dt.strftime(fmt)


# =============================================================================


def list_of_items(items, sep="and"):
    if len(items) == 0:
        return None
    if len(items) == 1:
        return str(items[0])
    if len(items) == 2:
        return (f" {sep} ").join(map(str, items))
    return ", ".join(map(str, items[:-1])) + f", {sep} " + str(items[-1])
