"""
General utilities.
"""

# =============================================================================

import json

import pytz

# =============================================================================

UTC_TZ = pytz.utc
EASTERN_TZ = pytz.timezone("US/Eastern")

DATETIME_FMT = "%Y-%m-%d %H:%M:%S"

# =============================================================================


def json_dump_compact(data, **kwargs):
    """Dumps the given data in the most compact JSON format."""
    kwargs.pop("separators", None)
    return json.dumps(data, separators=(",", ":"), **kwargs)


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
