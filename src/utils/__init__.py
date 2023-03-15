"""
General utilities.
"""

# =============================================================================

import json

# =============================================================================


def json_dump_compact(data, **kwargs):
    """Dumps the given data in the most compact JSON format."""
    kwargs.pop("separators", None)
    return json.dumps(data, separators=(",", ":"), **kwargs)
